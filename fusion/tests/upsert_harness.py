# Shared pieces for the overnight scenarios (upsert-test-scenarios.md): new tabs, a build, a snapshot of
# a design, and the § 2 checks that run after every scenario.
import json, os, re, time, traceback
import adsk.core, adsk.fusion
import cad_apprentice
from cad_apprentice import _attr, timeline_items

app = adsk.core.Application.get()
VOL_TOL = 1e-6  # part of the volume
BOX_TOL = 1e-4  # cm


class Failed(Exception):
    pass


def new_tab():
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    des = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
    des.designType = adsk.fusion.DesignTypes.ParametricDesignType
    return doc, des


# The helpers below take the scenario's note() as log, to name their work in it (fusion/rules.md).
def close_tab(doc, log=None):
    try:
        if doc and doc.isValid:
            with cad_apprentice.slow(log, 'close the tab without saving'):
                doc.close(False)
    except:
        pass


def design_of(doc):
    return adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))


def build(doc, des, describe, v, log_path, save_note=None, go_back_to=None):
    # One run of the script: a Builder, describe(b, v), finish(). Returns what the checks need.
    log = cad_apprentice.LiveLog(log_path)
    t0 = time.time()
    r = {'ok': False, 'error': None}
    b = None
    try:
        # Passed only when set, so the same tests also run on a library from before go_back_to.
        b = cad_apprentice.Builder(des, doc, log, **({'go_back_to': go_back_to} if go_back_to is not None else {}))
        r['builder'] = b
        describe(b, v)
        r['ok'] = b.finish()
        if r['ok'] and save_note:
            b.save(save_note)
    except Exception as err:
        r['error'] = str(err)
        r['trace'] = traceback.format_exc()
        if b is not None:
            try:
                b.abort(str(err))
            except:
                r['abort_error'] = traceback.format_exc()
    r['seconds'] = round(time.time() - t0, 2)
    r['log'] = list(log)
    log.close()
    if b is not None:
        r['counts'] = dict(b.counts)
        r['touched'] = list(b.touched)
        r['visited'] = list(b.visited)
        r['params_set'] = list(b.params_set)
        r['params_kept'] = list(b.params_kept)
        r['structure_changed'] = b.structure_changed
        r['readings'] = readings(b)
    return r


def readings(b):
    # What each step's value reader says about its feature now: the values Fusion really holds.
    out = {}
    for k, m in b.made.items():
        ent, read = b.known.get(k), m[6]
        if read is None or ent is None:
            continue
        try:
            out[k] = str(read(ent)) if ent.isValid else 'gone'
        except Exception as err:
            out[k] = 'unreadable: %s' % err
    return out


def same_value(um, got, want):
    # Fusion writes some values back its own way ("8.00 mm" for "0.8 cm"), so each part is compared by
    # value. The extra radii of a variable fillet can come back in any order.
    parts = lambda x: [p.strip() for p in x.replace(';', ',').split(',')]
    g, w = parts(got), parts(want)
    if len(g) != len(w):
        return False
    g, w = g[:2] + sorted(g[2:]), w[:2] + sorted(w[2:])
    for a, c in zip(g, w):
        if a == c:
            continue
        try:
            for x, y in zip(a.split('@'), c.split('@')):
                units = 'deg' if 'deg' in x + y else '' if x.replace('.', '').isdigit() else 'cm'
                if abs(um.evaluateExpression(x, units) - um.evaluateExpression(y, units)) > 1e-6:
                    return False
        except Exception:
            return False
    return True


def same_readings(um, a, b):
    # Lines for the steps whose value reader says something different in two builds.
    return ['%s reads %s | %s' % (k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b))
            if a.get(k) is None or b.get(k) is None or not same_value(um, a[k], b[k])]


# The one saved design the tests reuse (upsert-test-scenarios.md § 1): fusion_upsert test design, in a
# fusion_upsert tests folder inside Admin Project, never its root. Opened, cleared, saved, built on.
TEST_PROJECT, TEST_FOLDER, TEST_DESIGN = 'Admin Project', 'fusion_upsert tests', 'fusion_upsert test design'


def test_folder():
    data = app.data
    project = None
    for i in range(data.dataProjects.count):
        if data.dataProjects.item(i).name == TEST_PROJECT:
            project = data.dataProjects.item(i)
    if project is None:
        raise Exception('no %s' % TEST_PROJECT)
    # With a view such as My Editable Documents open in the Data panel, reading the active project
    # raises "InternalValidationError : group". The folder is reached without it anyway.
    try:
        active = data.activeProject
    except RuntimeError:
        active = None
    if active is None or active.id != project.id:
        try:
            data.activeProject = project
        except RuntimeError:
            pass
    root = project.rootFolder
    return root.dataFolders.itemByName(TEST_FOLDER) or root.dataFolders.add(TEST_FOLDER)


def latest_version(fid):
    return app.data.findFileById(fid).latestVersionNumber


# A save reaches the cloud a little later. Waits until the file has version n.
def wait_version(fid, n, seconds=120, log=None):
    with cad_apprentice.slow(log, 'wait for version %d to reach the cloud' % n):
        for i in range(seconds * 2):
            if latest_version(fid) >= n:
                return True
            adsk.doEvents()
            time.sleep(0.5)
    return False


def clear(des, log=None):
    tl = des.timeline
    with cad_apprentice.slow(log, 'clear the design: %d steps' % tl.count):
        for g in list(tl.timelineGroups):
            g.deleteMe(False)
        tl.moveToBeginning()
        tl.deleteAllAfterMarker()
    for i in range(20):  # a parameter goes once nothing uses it
        left = [p for p in des.userParameters]
        for p in left:
            try:
                p.deleteMe()
            except:
                pass
        if not des.userParameters.count:
            break
    for owner in (des, des.rootComponent):
        for a in [a for a in owner.attributes if a.groupName == cad_apprentice.GROUP]:
            a.deleteMe()


def file_of(doc):
    try:
        return doc.dataFile  # raises while the first save is still uploading
    except Exception:
        return None


def wait_file(doc, seconds=120, log=None):
    with cad_apprentice.slow(log, 'wait for the first save to reach the cloud'):
        for i in range(seconds * 2):
            if file_of(doc):
                return True
            adsk.doEvents()
            time.sleep(0.5)
    return False


def saved_tab(S):
    folder = test_folder()
    df = None
    for i in range(folder.dataFiles.count):
        if folder.dataFiles.item(i).name == TEST_DESIGN:
            df = folder.dataFiles.item(i)
    if df is None:
        doc, des = new_tab()
        S.tabs.append(doc)
        with cad_apprentice.slow(S.note, 'save the new test design'):
            doc.saveAs(TEST_DESIGN, folder, 'A design the fusion_upsert tests reuse. Safe to delete.', '')
        # Seen with the screen locked: the save starts and never uploads, most likely
        # because its thumbnail needs the viewport.
        if not wait_file(doc, log=S.note):
            raise Exception('the test design did not save in 120 s: a first save needs the Fusion window on screen')
    else:
        with cad_apprentice.slow(S.note, 'open the test design'):
            doc = app.documents.open(df)
        des = design_of(doc)
        S.tabs.append(doc)
    fid = file_of(doc).id
    clear(des, S.note)
    if doc.isModified:
        n = latest_version(fid)
        with cad_apprentice.slow(S.note, 'save the cleared design'):
            doc.save('cleared for %s' % S.sid)
        wait_version(fid, n + 1, log=S.note)
    return doc, des, fid


# After a go-back the tab is a new one: the run closed its tab and opened the saved version.
def reopened(S, fid):
    for d in app.documents:
        if d.isValid and file_of(d) and file_of(d).id == fid and d not in S.tabs:
            S.tabs.append(d)
            return d, design_of(d)
    for d in app.documents:
        if d.isValid and file_of(d) and file_of(d).id == fid:
            return d, design_of(d)
    return None, None


def changed(r):
    c = r.get('counts', {})
    return {k: c.get(k, 0) for k in ('created', 'updated', 'replaced', 'removed') if c.get(k, 0)}


def components(occs):
    return [{'occ': o.name, 'comp': o.component.name, 'children': components(o.childOccurrences)} for o in occs]


def snapshot(des):
    tl = des.timeline
    items = []
    for it in timeline_items(tl):
        e = it.entity
        items.append({
            'name': it.name, 'key': _attr(e, 'key') if e else None, 'fp': _attr(e, 'fp') if e else None,
            'group': it.parentGroup.name if it.parentGroup else None,
            'health': {0: 'ok', 1: 'warning', 2: 'error'}.get(it.healthState, str(it.healthState)),
            'message': it.errorOrWarningMessage if it.healthState else '',
            'suppressed': it.isSuppressed, 'type': e.objectType.split('::')[-1] if e else None,
        })
    groups = {g.name: g.isCollapsed for g in tl.timelineGroups}
    bodies = []
    for comp in des.allComponents:
        # Fusion names the root component after the document and its version ("... v12", or
        # "(Unsaved)"), so a save would look like a change. Every root is called '(root)' here.
        cname = '(root)' if comp == des.rootComponent else comp.name
        for i in range(comp.bRepBodies.count):
            body = comp.bRepBodies.item(i)
            bb = body.boundingBox
            bodies.append({'comp': cname, 'name': body.name, 'volume': body.volume,
                           'min': [bb.minPoint.x, bb.minPoint.y, bb.minPoint.z], 'max': [bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z]})
    bodies.sort(key=lambda x: (x['comp'], x['name'], x['volume']))
    params = {}
    for p in des.userParameters:
        params[p.name] = {'expression': p.expression, 'comment': p.comment, 'favorite': p.isFavorite, 'value': p.value, 'unit': p.unit}
    return {'items': items, 'groups': groups, 'tree': components(des.rootComponent.occurrences), 'bodies': bodies,
            'params': params, 'marker': tl.markerPosition, 'count': tl.count}


def health(snap, allow=()):
    return ['%s: %s %s' % (i['name'], i['health'], i['message']) for i in snap['items'] if i['health'] != 'ok' and i['name'] not in allow]


def compare(a, b, ignore_items=(), ignore_params=(), ignore_bodies=(), ignore_groups=(), fp=False, collapsed=False):
    # What differs between two snapshots, as plain lines. fp=True also compares the stored fingerprints
    # (for a rerun in the same tab; a fresh build in another tab has the same ones anyway).
    out = []
    keep = lambda s: [dict(i) for i in s['items'] if i['name'] not in ignore_items]
    ia, ib = keep(a), keep(b)
    cols = ['name', 'key', 'group', 'type'] + (['fp', 'suppressed'] if fp else [])
    la = [tuple(i[c] for c in cols) for i in ia]
    lb = [tuple(i[c] for c in cols) for i in ib]
    if la != lb:
        n = max(len(la), len(lb))
        for k in range(n):
            x = la[k] if k < len(la) else None
            y = lb[k] if k < len(lb) else None
            if x != y:
                out.append('timeline %d: %s | %s' % (k, x, y))
                if len(out) > 12:
                    out.append('...')
                    break
    ga = {g: c for g, c in a['groups'].items() if g not in ignore_groups}
    gb = {g: c for g, c in b['groups'].items() if g not in ignore_groups}
    if set(ga) != set(gb):
        out.append('groups: %s | %s' % (sorted(ga), sorted(gb)))
    elif collapsed and ga != gb:
        out.append('collapsed: %s | %s' % (ga, gb))
    if a['tree'] != b['tree']:
        out.append('components: %s | %s' % (json.dumps(a['tree']), json.dumps(b['tree'])))
    ba = [x for x in a['bodies'] if x['name'] not in ignore_bodies]
    bb = [x for x in b['bodies'] if x['name'] not in ignore_bodies]
    if [(x['comp'], x['name']) for x in ba] != [(x['comp'], x['name']) for x in bb]:
        out.append('bodies: %s | %s' % ([(x['comp'], x['name']) for x in ba], [(x['comp'], x['name']) for x in bb]))
    else:
        for x, y in zip(ba, bb):
            if abs(x['volume'] - y['volume']) > VOL_TOL * max(abs(x['volume']), 1e-9):
                out.append('volume of %s/%s: %.9g | %.9g' % (x['comp'], x['name'], x['volume'], y['volume']))
            if any(abs(p - q) > BOX_TOL for p, q in zip(x['min'] + x['max'], y['min'] + y['max'])):
                out.append('box of %s/%s: %s | %s' % (x['comp'], x['name'], [round(p, 5) for p in x['min'] + x['max']], [round(p, 5) for p in y['min'] + y['max']]))
    pa = {k: v for k, v in a['params'].items() if k not in ignore_params}
    pb = {k: v for k, v in b['params'].items() if k not in ignore_params}
    if set(pa) != set(pb):
        out.append('parameters: %s | %s' % (sorted(pa), sorted(pb)))
    for k in sorted(set(pa) & set(pb)):
        for f in ('expression', 'comment', 'favorite'):
            x, y = pa[k][f], pb[k][f]
            if f == 'expression' and cad_apprentice._same(x, y):
                continue
            if x != y:
                out.append('parameter %s %s: %r | %r' % (k, f, x, y))
    return out


def log_honest(r):
    # The counts match the per-step lines, and every line gives a reason.
    out = []
    c = r.get('counts', {})
    touched = r.get('touched', [])
    for what in ('created', 'updated', 'replaced', 'removed'):
        n = len([t for t in touched if t[0] == what])
        if n != c.get(what, 0):
            out.append('%d %s but %d lines say so' % (c.get(what, 0), what, n))
    for what, name, why in touched:
        if not why:
            out.append('%s %s gives no reason' % (what, name))
    return out


# A timeline item's name as the log gives it: an occurrence's item is ' Outer:1', the log says Outer.
def plain(name):
    return re.sub(r':\d+$', '', name.strip()) if name else name


def design_unlogged(before, after, r):
    # The log against the design itself, not against the library's own records: an item without a
    # key that came or went, or bodies that changed while the log says nothing changed. A run that
    # started with the marker rolled back sees less of the design, so it isn't compared.
    if before['marker'] != before['count']:
        return []
    out = []
    log = r.get('log', [])
    na = [plain(i['name']) for i in before['items'] if not i['key']]
    nb = [plain(i['name']) for i in after['items'] if not i['key']]
    for name in sorted(set(na) | set(nb)):
        if na.count(name) != nb.count(name) and not any(name in line for line in log):
            out.append('%s without a key %s and the log says nothing' % (name, 'came' if nb.count(name) > na.count(name) else 'went'))
    # A part the log says it renamed counts under its new name. Not a body: "renamed" names a step, and a
    # body can share its step's old name without being renamed (E12's Stock).
    renamed = dict(m.groups() for m in (re.match(r'renamed (.+) to (.+)$', l) for l in log) if m)
    bodies = lambda s, ren: sorted((ren.get(x['comp'], x['comp']), x['name'], round(x['volume'], 6)) for x in s['bodies'])
    if not changed(r) and not r.get('params_set') and bodies(before, renamed) != bodies(after, {}):
        out.append('the bodies changed, but the log says nothing changed: %s | %s' % (bodies(before, renamed), bodies(after, {})))
    return out


def unlogged(before, after, r):
    # Keyed steps whose fingerprint or presence changed, but which no log line names.
    named = set(t[1] for t in r.get('touched', []))
    named |= set(n for line in r.get('log', []) for n in [line] if line.startswith('moved '))
    if before['marker'] != before['count']:
        return []  # Rolled back at the start: the items past the marker read as unmarked.
    fa = {i['key']: (i['fp'], plain(i['name'])) for i in before['items'] if i['key']}
    fb = {i['key']: (i['fp'], plain(i['name'])) for i in after['items'] if i['key']}
    # A renamed parameter changes the fingerprint of every step that names it, and the step stays.
    param_renamed = any(' renamed to ' in p for p in r.get('params_set', []))
    out = []
    for k in set(fa) | set(fb):
        x, y = fa.get(k), fb.get(k)
        if x is not None and y is not None and x[0] != y[0] and param_renamed:
            continue
        if x is None or y is None or x[0] != y[0]:
            names = set(n for n in (x[1] if x else None, y[1] if y else None) if n)
            if not names & named and not any(n in line for n in names for line in r.get('log', [])):
                out.append('%s changed (%s -> %s) and the log says nothing' % (k, x, y))
    return out


def timeline_health(des):
    # Every timeline item that is not healthy, as a line.
    bad = []
    for it in timeline_items(des.timeline):
        if it.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
            bad.append('%s: %s %s' % (it.name, it.healthState, it.errorOrWarningMessage))
    return bad


class Verdict:
    # The pass or fail of a test file that builds a design a few times (test_features, test_edit_in_place,
    # test_joints). Before, those files only printed what happened and a person read it.
    def __init__(self):
        self.fails = []

    def expect(self, ok, line):
        if not ok:
            self.fails.append(line)
        return ok

    # One build, label v1/v2/...: no error, every feature healthy, and the steps the log names are the
    # ones expected. first: everything is created. want: {name: 'updated'} for the steps the change
    # should reach; may_replace: names that may be replaced instead, if the log says why. want=None with
    # first=False: a rerun, where nothing may change.
    def run(self, label, r, des, first=False, want=None, may_replace=()):
        if not self.expect(not r.get('error'), '%s: the run failed: %s' % (label, r.get('error'))):
            return False
        for line in timeline_health(des):
            self.fails.append('%s: not healthy: %s' % (label, line))
        touched = {name: what for what, name, why in r.get('touched', [])}
        whys = {name: why for what, name, why in r.get('touched', [])}
        reasons = [l for l in r.get('log', []) if l.startswith('could not edit ')]
        if first:
            self.expect(set(touched.values()) <= {'created'} and r['counts'].get('created') == len(r.get('visited', [])),
                        '%s: a first build should create every step: %s' % (label, r.get('counts')))
            return True
        want = want or {}
        for name, what in sorted(touched.items()):
            if name not in want:
                self.fails.append('%s: %s was %s, but nothing it uses changed' % (label, name, what))
            elif what == 'replaced' and name not in may_replace:
                self.fails.append('%s: %s was replaced, not edited in place' % (label, name))
            elif what == 'replaced' and not any(name in l for l in reasons) and "can't be edited in place" not in whys[name] \
                    and 'replaced' not in want[name]:
                self.fails.append('%s: %s was replaced and the log does not say why' % (label, name))
        for name in sorted(set(want) - set(touched)):
            self.fails.append('%s: %s should be %s, but the run left it as it was' % (label, name, want[name]))
        for line in reasons:
            if not any(n in line for n in may_replace):
                self.fails.append('%s: %s' % (label, line))
        return True

    def result(self, **more):
        out = {'status': 'fail' if self.fails else 'pass', 'fails': self.fails}
        out.update(more)
        return out


class Scenario:
    # One scenario: its own tabs, its runs, its checks. Everything goes into self.result.
    def __init__(self, sid, out_dir, describe, note):
        self.sid, self.describe, self.note = sid, describe, note
        self.dir = os.path.join(out_dir, sid)
        os.makedirs(self.dir, exist_ok=True)
        self.tabs = []
        self.runs = 0
        self.fails = []
        self.flags = []
        self.info = {}
        self.checks = {}

    def tab(self):
        doc, des = new_tab()
        self.tabs.append(doc)
        return doc, des

    def run(self, doc, des, v, label='', save_note=None, go_back_to=None):
        self.runs += 1
        path = os.path.join(self.dir, '%02d%s.log' % (self.runs, '-' + label if label else ''))
        self.note('%s run %d %s' % (self.sid, self.runs, label))
        before = snapshot(des)
        r = build(doc, des, self.describe, v, path, save_note, go_back_to)
        r['label'] = label
        # The design before and after, for the log checks in standard().
        r['before'], r['after'] = before, snapshot(des) if des.isValid else None
        self.info.setdefault('runs', []).append({k: r.get(k) for k in ('label', 'ok', 'error', 'seconds', 'counts')})
        return r

    def fail(self, line):
        self.fails.append(line)

    def flag(self, line):
        self.flags.append(line)

    def expect(self, ok, line):
        if not ok:
            self.fail(line)
        return ok

    def need(self, r, what='run'):
        if not r['ok']:
            raise Failed('%s failed: %s %s' % (what, r.get('error') or '', [l for l in r['log'] if 'BROKEN' in l or 'STOPPED' in l]))

    def check(self, name, problems):
        self.checks[name] = 'pass' if not problems else problems
        for p in problems:
            self.fail('%s: %s' % (name, p))

    # § 2, after the scenario's last run r in (doc, des), built from variant v.
    #   hand: names of features made by hand, which must survive.  allow_health: names expected to warn.
    #   fresh_tweak(des): the hand edits again on the fresh build, so it can be compared.
    def standard(self, doc, des, v, r, hand=(), allow_health=(), fresh_tweak=None, ignore=None, rerun=True, fresh=True):
        ignore = ignore or {}
        snap = snapshot(des)
        self.check('1 healthy', health(snap, allow=tuple(allow_health)))
        if fresh:
            fdoc, fdes = self.tab()
            fr = self.run(fdoc, fdes, v, 'fresh')
            if fresh_tweak:
                fresh_tweak(fdes)
            fsnap = snapshot(fdes)
            diff = compare(snap, fsnap, ignore_items=tuple(hand) + tuple(ignore.get('items', ())), ignore_params=ignore.get('params', ()), ignore_bodies=ignore.get('bodies', ()), ignore_groups=ignore.get('groups', ()))
            if not fr['ok']:
                diff.insert(0, 'the fresh build failed: %s' % fr.get('error'))
            self.check('2 same as fresh', diff)
            close_tab(fdoc, self.note)
        present = {i['name']: i for i in snap['items']}
        self.check('4 hand work survives', ['%s is gone' % n for n in hand if n not in present] + ['%s is %s' % (n, present[n]['health']) for n in hand if n in present and present[n]['health'] != 'ok'])
        keys = set(i['key'] for i in snap['items'] if i['key'])
        lost = ['step %s is gone' % k for k in r.get('visited', []) if k not in keys]
        foreign = ['%s has no key' % i['name'] for i in snap['items'] if not i['key'] and i['name'] not in hand]
        self.check('5 no lost steps', lost + foreign)
        honest = log_honest(r)
        if r.get('before') and r.get('after'):
            honest += unlogged(r['before'], r['after'], r) + design_unlogged(r['before'], r['after'], r)
        self.check('6 log honest', honest)
        if rerun:
            doc.activate()
            r2 = self.run(doc, des, v, 'rerun')
            snap2 = snapshot(des)
            problems = [] if r2['ok'] else ['the rerun failed: %s' % r2.get('error')]
            problems += ['the rerun %s' % changed(r2)] if changed(r2) else []
            problems += ['the rerun moved: %s' % l for l in r2['log'] if l.startswith('moved ')]
            problems += ['the rerun set parameters: %s' % r2['params_set']] if r2.get('params_set') else []
            problems += compare(snap, snap2, fp=True, collapsed=True)
            self.check('3 rerun changes nothing', problems)
            self.info['rerun_seconds'] = r2['seconds']
            if r2['seconds'] > 5:
                self.flag('8 time: a no-change rerun took %.1f s' % r2['seconds'])
        return snap

    def close(self):
        for d in self.tabs:
            close_tab(d, self.note)

    def result(self, error=None):
        status = 'error' if error else ('fail' if self.fails else 'pass')
        return {'id': self.sid, 'status': status, 'fails': self.fails, 'flags': self.flags, 'error': error,
                'checks': self.checks, 'info': self.info}
