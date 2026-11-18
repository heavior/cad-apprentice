"""Clean up before a Fusion script run and collect its outputs after, in one allowed command each.

Each run used to take a hand-written shell line with `rm`, which asked for permission every time.
This script is on the allow list in .claude/settings.json, so it runs without asking. It only touches the
script's own folder in Fusion's Scripts folder and the project's output folders.

Usage:
  python3 ~/cad-apprentice/fusion/tools/fusion_outputs.py prep NAME --mode new|saved|clean|check|night|check:<names>|probe:<file>
  python3 ~/cad-apprentice/fusion/tools/fusion_outputs.py run NAME --mode ... [--wait MINUTES]
  python3 ~/cad-apprentice/fusion/tools/fusion_outputs.py collect NAME PROJECT_DIR [--prune]
  python3 ~/cad-apprentice/fusion/tools/fusion_outputs.py new NAME PROJECT_DIR --doc "Design name"

prep     reads the script's code first (precheck.py, on the folder the entry file's
         CODE line names, and on the library) and stops on a problem, so a run never starts on a
         mistake these cheap checks can find. --no-check skips that. Then it deletes
         last run's log, pictures, STLs, probe scripts and stop file, writes mode.txt, leaves an empty
         log, and brings Fusion to the front.
run      does prep, then has the UpsertTestRunner add-in run the script: no click on ▶, and it works
         behind a locked screen. It prints the log as it grows and stops when the
         add-in writes its result, or after --wait minutes (default 30) with no new log line; then it
         names the Fusion call the run is stuck in, from the log's .now file. Exit 0
         only when the log ends in DONE and has no TRIAL FAILED, RANGE TOO WIDE, RERUN CHANGED
         SOMETHING or LOOSE PIECES line. Run it in the background; a big design takes minutes. One
         run per design at a time (run.lock). Stopped before Fusion starts it, it takes its request
         back; the runner also refuses a request older than --wait.
collect  copies the STLs to PROJECT_DIR/stl, view_*.png to pictures/ and sketch_*.png to
         pictures/sketches/, then lists the files there that this run didn't make. --prune
         deletes those from disk.
new      starts a design from fusion/template/: writes the entry file NAME.py, its NAME.manifest and a
         starter build.py to PROJECT_DIR/scripts/fusion/NAME/, and copies the entry file and manifest to
         Fusion's Scripts folder. --doc is the name the design is saved under in Fusion. Then
         `run NAME --mode new` builds and saves it once; every round after that is `--mode saved`.
"""
import argparse, glob, json, os, random, re, shutil, signal, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
LIB = os.path.join(KIT, 'lib', 'cad_apprentice')
sys.path.insert(0, LIB)
import precheck

RUN = os.path.join(KIT, 'tests', 'run')
TEMPLATE = os.path.join(KIT, 'template')
SCRIPTS = os.path.expanduser('~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts')
# What a run leaves in its folder. Anything else there (the entry file, the manifest) stays.
OLD = ('*.log', '*.now', '*.png', '*.stl', 'probe_*.py', 'stop')
# Log lines that mean a check failed, though the build itself got to DONE.
FAILED = ('TRIAL FAILED', 'RANGE TOO WIDE', 'RERUN CHANGED SOMETHING', 'LOOSE PIECES')
# Output pattern -> folder inside the project.
OUT = (('*.stl', 'stl'), ('view_*.png', 'pictures'), ('sketch_*.png', 'pictures/sketches'))


def script_dir(name):
    d = os.path.join(SCRIPTS, name)
    if not os.path.isfile(os.path.join(d, name + '.py')):
        sys.exit('no Fusion script %s at %s' % (name, d))
    return d


def code_dir(d, name):
    # The folder the entry file runs code from: its REPO = os.path.expanduser('...') and
    # CODE = os.path.join(REPO, '...') lines.
    text = open(os.path.join(d, name + '.py'), encoding='utf-8').read()
    repo = re.search(r"^REPO = os\.path\.expanduser\('([^']+)'\)", text, re.M)
    m = re.search(r"^CODE = os\.path\.join\(REPO, '([^']+)'\)", text, re.M)
    if repo and m:
        return os.path.join(os.path.expanduser(repo.group(1)), m.group(1))
    print("couldn't find the REPO and CODE lines in the entry file; only the Scripts folder was checked")
    return d


def checks(d, name):
    # precheck on the script's code and the library. Returns the problems.
    code = code_dir(d, name)
    paths = list(precheck.files([code, LIB]))
    keys = {p: precheck.literal_keys(p) for p in paths if p.startswith(code)}
    found = []
    for p in paths:
        if p in keys:
            found += precheck.check(p, set().union(*(k for q, k in keys.items() if q != p)))[0]
    print('checked %d files in %s: %s' % (len(keys), os.path.relpath(code),
                                         '%d problems' % len(found) if found else 'no problems'))
    return found


def prep(a, front=True):
    d = script_dir(a.name)
    if not a.no_check:
        found = checks(d, a.name)
        if found:
            sys.exit('fix these first (or --no-check):\n' + '\n'.join(found))
    gone = [p for pat in OLD for p in glob.glob(os.path.join(d, pat))]
    for p in gone:
        os.remove(p)
    open(os.path.join(d, 'mode.txt'), 'w').write(a.mode + '\n')
    # The entry file runs a probe once and puts mode.txt back to saved itself.
    open(os.path.join(d, a.name + '.log'), 'w').close()
    if front:
        subprocess.run(['osascript', '-e', 'tell application id "com.autodesk.fusion360" to activate'], check=False)
    print('cleared %d old files, mode %s, empty log%s' % (len(gone), a.mode, ', Fusion in front' if front else ''))


def lock(d, rid):
    # One run of a design at a time: a second one's prep would delete the first one's log and pictures.
    path = os.path.join(d, 'run.lock')
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, ('%d %s' % (os.getpid(), rid)).encode())
            os.close(fd)
            return path
        except FileExistsError:
            try:
                pid = int(open(path).read().split()[0])
                os.kill(pid, 0)
            except (ProcessLookupError, ValueError, IndexError):
                os.remove(path)  # left by a run that was killed
                continue
            sys.exit('%s is already running (pid %d)' % (os.path.basename(d), pid))
    sys.exit("couldn't take %s" % path)


def run(a):
    d = script_dir(a.name)
    rid = '%s-%s-%04x' % (a.name, time.strftime('%Y%m%d-%H%M%S'), random.getrandbits(16))
    held = lock(d, rid)
    # A killed shell sends SIGTERM or SIGHUP; turn them into an exit, so the finally below withdraws the request.
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit('stopped'))
    queued = os.path.join(RUN, 'requests', rid + '.json')
    result = os.path.join(RUN, 'results', rid + '.json')
    try:
        prep(a, front=False)
        log = os.path.join(d, a.name + '.log')
        # The runner refuses the request after this, so one left behind can't start hours later.
        req = {'id': rid, 'file': 'tools/run_design.py', 'args': {'name': a.name}, 'no_resume': True,
               'expires': time.time() + a.wait * 60}
        os.makedirs(os.path.join(RUN, 'requests'), exist_ok=True)
        json.dump(req, open(queued[:-5] + '.tmp', 'w'))
        os.replace(queued[:-5] + '.tmp', queued)
        print('request %s sent to the runner' % rid, flush=True)
        seen, size, last = 0, 0, time.time()
        while not os.path.exists(result):
            time.sleep(3)
            text = open(log, encoding='utf-8').read() if os.path.exists(log) else ''
            lines = text.splitlines()
            if len(text) < size:
                print('--- the log was replaced; all of it:', flush=True)
                seen = 0
            size = len(text)
            if len(lines) > seen:
                print('\n'.join(lines[seen:]), flush=True)
                seen, last = len(lines), time.time()
            if time.time() - last > a.wait * 60:
                now = open(log + '.now', encoding='utf-8').read().strip() if os.path.exists(log + '.now') else ''
                if now:
                    sys.exit('no new log line for %d minutes. The last Fusion call started: %s' % (a.wait, now))
                sys.exit('no new log line for %d minutes. Is Fusion up, with the UpsertTestRunner add-in running? '
                         'Its log: %s' % (a.wait, os.path.join(RUN, 'runner.log')))
        text = open(log, encoding='utf-8').read() if os.path.exists(log) else ''
        lines = text.splitlines()
        if len(text) < size:
            print('--- the log was replaced; all of it:')
            seen = 0
        print('\n'.join(lines[seen:]))
        r = json.load(open(result))
        if r.get('status') != 'done':
            sys.exit('runner: %s\n%s' % (r.get('status'), r.get('error', '')))
        if not (r.get('result') or {}).get('done'):
            sys.exit('the log does not end in DONE')
        # The build got to DONE, but a check after it can still have failed.
        # Log lines start with the time, "12:47:30 TRIAL FAILED: ...".
        bad = [l for l in lines if re.sub(r'^\d\d:\d\d:\d\d ', '', l).lstrip().startswith(FAILED)]
        if bad:
            sys.exit('CHECK FAILED: %d lines\n%s' % (len(bad), '\n'.join(bad)))
        print('runner: done in %s s' % r.get('seconds'))
    finally:
        if os.path.exists(queued):
            os.remove(queued)
            print('request withdrawn, nothing ran')
        elif not os.path.exists(result) and os.path.exists(os.path.join(RUN, 'active', rid + '.json')):
            print('the run already started in Fusion; it will finish there')
        os.remove(held)


def collect(a):
    d = script_dir(a.name)
    proj = os.path.abspath(a.project)
    stale = []
    for pat, sub in OUT:
        dest = os.path.join(proj, sub)
        new = {os.path.basename(p) for p in glob.glob(os.path.join(d, pat))}
        if not new:
            continue
        os.makedirs(dest, exist_ok=True)
        for f in sorted(new):
            shutil.copy2(os.path.join(d, f), dest)
        print('%-18s %d files' % (sub + '/', len(new)))
        stale += [p for p in glob.glob(os.path.join(dest, pat)) if os.path.basename(p) not in new]
    if not stale:
        print('nothing stale')
        return
    rel = [os.path.relpath(p, proj) for p in sorted(stale)]
    print('not made by this run:\n  ' + '\n  '.join(rel))
    if a.prune:
        for p in rel:
            os.remove(os.path.join(proj, p))
        print('pruned %d' % len(rel))


def new(a):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', a.name):
        sys.exit('%s: a name of letters, digits and _ (it becomes a Python file name)' % a.name)
    code = os.path.join(os.path.abspath(a.project), 'scripts', 'fusion', a.name)
    fusion = os.path.join(SCRIPTS, a.name)
    for d in (code, fusion):
        if os.path.exists(d):
            sys.exit('%s is already there; pick another name or remove it first' % d)
    top = os.path.abspath(a.project)
    home = lambda p: '~' + p[len(os.path.expanduser('~')):] if p.startswith(os.path.expanduser('~') + os.sep) else p
    if re.search(r"['\"\\]", a.doc):
        sys.exit("%s: a design name without ' \" or \\ (it goes into Python and JSON as is)" % a.doc)
    fill = {'__NAME__': a.name, '__DOC__': a.doc, '__REPO__': home(top),
            '__CODE__': os.path.relpath(code, top), '__LIB__': home(os.path.join(KIT, 'lib'))}
    os.makedirs(code)
    for src, dest in (('Entry.py', a.name + '.py'), ('Entry.manifest', a.name + '.manifest'), ('build.py', 'build.py')):
        text = open(os.path.join(TEMPLATE, src), encoding='utf-8').read()
        for k, v in fill.items():
            text = text.replace(k, v)
        open(os.path.join(code, dest), 'w', encoding='utf-8').write(text)
    os.makedirs(fusion)
    for f in (a.name + '.py', a.name + '.manifest'):
        shutil.copy2(os.path.join(code, f), fusion)
    print('wrote %s/: %s.py, %s.manifest, build.py' % (os.path.relpath(code), a.name, a.name))
    print('copied the entry file and manifest to %s' % fusion)
    print('next: edit build.py, then run %s --mode new once; after that --mode saved' % a.name)


MODES = ('new', 'saved', 'clean', 'check', 'night')


def mode(text):
    # check:wall,height (or night:...) runs the parameter test on those parameters only;
    # check:extremes or check:random=50,seed=7 picks its stages. The design script splits it with
    # cad_apprentice.split_mode(). probe:<file> runs a throwaway test script once, in place of the design.
    m, _, names = text.partition(':')
    if m == 'probe':
        if not os.path.isfile(names):
            raise argparse.ArgumentTypeError('probe:%s: no such file' % names)
        return text
    if m not in MODES or (_ and (m not in ('check', 'night') or not names.strip(','))):
        raise argparse.ArgumentTypeError('%s: one of %s, or check:<names and tests> / night:<names and tests>' % (text, ', '.join(MODES)))
    return text


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prep')
    p.add_argument('name')
    # No default mode: 'new' saves another copy under the same name when the design is already saved
    # (once, two copies of one design after runs without --mode).
    p.add_argument('--mode', required=True, type=mode)
    p.add_argument('--no-check', action='store_true')
    r = sub.add_parser('run')
    r.add_argument('name')
    r.add_argument('--mode', required=True, type=mode)
    r.add_argument('--no-check', action='store_true')
    r.add_argument('--wait', type=float, default=30)
    c = sub.add_parser('collect')
    c.add_argument('name')
    c.add_argument('project')
    c.add_argument('--prune', action='store_true')
    n = sub.add_parser('new')
    n.add_argument('name')
    n.add_argument('project')
    n.add_argument('--doc', required=True)
    a = ap.parse_args()
    {'prep': prep, 'run': run, 'collect': collect, 'new': new}[a.cmd](a)


if __name__ == '__main__':
    main()
