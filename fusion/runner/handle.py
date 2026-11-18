# Runs one request from run/requests/. Read from the repo on every request, so a fix here needs no
# Fusion restart. A request is JSON: {"id": ..., "file": <a .py, relative to the kit folder, or a full path>, "func": "main",
# "args": {...}}. The file is run fresh, with cad_apprentice and the test modules (upsert_*) reloaded,
# and func(args) gives the result. The result goes to run/results/<id>.json, with the time and the
# open tabs before and after. A result with "status" "pass" or "fail" sets the request's status; any
# other result that returns is "done". An id used before has its old files cleared first, so a rerun
# never reads the last run's files as its own. A request left in run/active/ was cut off by a crash: it runs again with
# args['resume'] set and its crash count up by one, unless it says "no_resume": true, and at most
# twice. A request past its "expires" time (seconds since 1970) is refused, not run. A file that isn't
# JSON goes to run/bad/. Any error in this file is written as the request's result, so nothing is
# picked up again and again (once, 109 times in 3 minutes).
import json, os, shutil, sys, time, traceback

KIT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
LIB = os.path.join(KIT, 'lib')
TESTS = os.path.join(KIT, 'tests')


def tabs(app):
    out = []
    for i in range(app.documents.count):
        d = app.documents.item(i)
        # A tab whose first save is still uploading, or failed, has no file Fusion can name yet.
        try:
            fid = d.dataFile.id if d.dataFile else None
        except RuntimeError as err:
            fid = 'unknown: %s' % err
        out.append({'name': d.name, 'file': fid, 'modified': d.isModified})
    return out


def write(path, data):
    # Written whole, then renamed, so a reader never sees half a file.
    with open(path + '.tmp', 'w') as f:
        json.dump(data, f, indent=1, default=str)
    os.replace(path + '.tmp', path)


def finish(name, rid, req, status, error, active, results):
    write(os.path.join(results, rid + '.json'), {'id': rid, 'request': req, 'status': status, 'error': error})
    os.remove(os.path.join(active, name))
    note('%s: %s' % (rid, status))


def handle(app):
    requests, active, results = (os.path.join(RUN, d) for d in ('requests', 'active', 'results'))
    for d in (active, results):
        os.makedirs(d, exist_ok=True)
    left = sorted(n for n in os.listdir(active) if n.endswith('.json'))
    if left:
        name = left[0]
    else:
        waiting = sorted(n for n in os.listdir(requests) if n.endswith('.json'))
        if not waiting:
            return
        name = waiting[0]
        os.replace(os.path.join(requests, name), os.path.join(active, name))
    rid, req = name[:-len('.json')], None
    try:
        req = json.load(open(os.path.join(active, name)))
        rid = req.get('id', rid)
        if left:
            if req.get('no_resume'):
                # A design run cut off by a quit is reported, not run again: the person may have quit Fusion
                # to stop it (once, a stuck bridge run restarted by itself when Fusion came back).
                return finish(name, rid, req, 'cut off', 'Fusion quit or crashed during the run', active, results)
            if req.get('crashes', 0) >= 2:
                return finish(name, rid, req, 'crashed twice', 'cut off twice; not run again', active, results)
            req['crashes'] = req.get('crashes', 0) + 1
            req.setdefault('args', {})['resume'] = True
            write(os.path.join(active, name), req)
            note('picking up %s after a crash (%d)' % (name, req['crashes']))
        elif req.get('expires') and time.time() > req['expires']:
            return finish(name, rid, req, 'expired', 'nobody was waiting for it any more', active, results)
        run(app, name, rid, req, active, results, resumed=bool(left))
    except:
        err = traceback.format_exc()
        if req is None:
            os.makedirs(os.path.join(RUN, 'bad'), exist_ok=True)
            os.replace(os.path.join(active, name), os.path.join(RUN, 'bad', name))
            write(os.path.join(results, rid + '.json'), {'id': rid, 'status': 'unreadable', 'error': err})
            note('%s is unreadable, moved to bad/:\n%s' % (name, err))
        elif os.path.exists(os.path.join(active, name)):
            finish(name, rid, req, 'runner error', err, active, results)


def run(app, name, rid, req, active, results, resumed=False):
    note('running %s' % rid)
    result = {'id': rid, 'request': req, 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'tabs_before': tabs(app)}
    t0 = time.time()
    # A crash or forced quit loses every unsaved tab, so nothing runs while one of the person's has changes.
    unsaved = [t['name'] for t in result['tabs_before'] if t['modified']]
    if unsaved:
        result['status'] = 'refused'
        result['error'] = 'tabs with unsaved changes: %s' % ', '.join(unsaved)
    else:
        try:
            if LIB not in sys.path:
                sys.path.insert(0, LIB)
            if TESTS not in sys.path:
                sys.path.insert(0, TESTS)
            # cad_apprentice's submodules too, or an edited helpers.py isn't picked up.
            for m in [m for m in sys.modules if m == 'cad_apprentice' or m.startswith('cad_apprentice.') or m.startswith('upsert_')]:
                del sys.modules[m]
            path = os.path.join(KIT, req['file'])
            out = os.path.join(results, rid)
            if os.path.isdir(out) and not resumed:
                # A run picked up after a crash keeps its files: the suite skips the scenarios it finished.
                old = sum(len(f) for _, _, f in os.walk(out))
                shutil.rmtree(out)
                result['cleared'] = '%d files from an earlier run with this id' % old
            os.makedirs(out, exist_ok=True)
            scope = {'__name__': 'upsert_request_' + rid, '__file__': path, 'OUT_DIR': out, 'REQUEST': req}
            exec(compile(open(path, encoding='utf-8').read(), path, 'exec'), scope)
            result['result'] = scope[req.get('func', 'main')](req.get('args', {}))
            got = result['result'].get('status') if isinstance(result['result'], dict) else None
            result['status'] = got if got in ('pass', 'fail') else 'done'
        except:
            result['status'] = 'error'
            result['error'] = traceback.format_exc()
    # A script that never closed its log leaves the library's timers on every Fusion call; take them off.
    if 'cad_apprentice' in sys.modules:
        try:
            sys.modules['cad_apprentice'].wrap_fusion(False)
        except:
            result['unwrap_error'] = traceback.format_exc()
    result['seconds'] = round(time.time() - t0, 1)
    try:
        result['tabs_after'] = tabs(app)
    except:
        result['tabs_after'] = traceback.format_exc()
    write(os.path.join(results, rid + '.json'), result)
    os.remove(os.path.join(active, name))
    note('finished %s: %s in %.0f s' % (rid, result['status'], result['seconds']))
