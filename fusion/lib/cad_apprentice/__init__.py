# Shared upsert library for Fusion build scripts. See README.md.
# A build script says what should exist, in timeline order. Rerunning it updates
# the design and leaves alone anything this library didn't create.

import hashlib, itertools, json, os, random, re, time
import adsk.core, adsk.fusion
import sys
sys.modules.pop(__name__ + '.precheck', None)  # Fusion keeps Python running between scripts: drop the last run's copy too.
sys.modules.pop(__name__ + '.helpers', None)
sys.modules.pop(__name__ + '.ranges', None)
from . import precheck, ranges

GROUP = 'fusion_upsert'  # The library's old name. Every saved design keeps its keys under it, so it stays.
Healthy = adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState
ErrorState = adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState
WarningState = adsk.fusion.FeatureHealthStates.WarningFeatureHealthState


def _same(a, b):
    return re.sub(r'\s', '', a) == re.sub(r'\s', '', b)


class LiveLog(list):
    # A log list that also writes each line to the file as it comes, with the time, so a long run can be
    # watched with tail -f instead of waiting blind for the end.
    def __init__(self, path):
        list.__init__(self)
        self._file = open(path, 'w')

    def append(self, line):
        list.append(self, line)
        self.progress(line)

    # A line for the file only: what the run is about to do. If Fusion freezes or crashes, the last
    # line names the step it was in, and the lines above show what got done.
    def progress(self, line):
        self._file.write('%s %s\n' % (time.strftime('%H:%M:%S'), line))
        self._file.flush()

    def close(self):
        self._file.close()


def progress(log, line):
    # Writes a progress line when the log is a LiveLog, or a function that writes one; a plain list
    # keeps only the results.
    if hasattr(log, 'progress'):
        log.progress(line)
    elif callable(log):
        log(line)


class slow:
    # Goes around every Fusion call that can take long: anything that makes Fusion recompute (a parameter
    # or feature edit, a timeline move, a delete), a save, an open, an export, a doEvents. A line before
    # says what's next; one after gives the time when it took a second or more. So a run that hangs names
    # the call it hangs in, and a slow run shows where the time went. check_slow.py
    # finds slow calls that have no slow() around them.
    def __init__(self, log, what):
        self.log, self.what = log, what

    def __enter__(self):
        progress(self.log, self.what)
        self.t0 = time.time()
        return self

    def __exit__(self, kind, err, tb):
        took = time.time() - self.t0
        if kind is not None:
            progress(self.log, '%s: failed after %.1f s' % (self.what, took))
        elif took >= 1:
            progress(self.log, '%s: done in %.1f s' % (self.what, took))


def set_param(log, p, expr):
    # Fusion recomputes everything that uses the parameter before this returns.
    with slow(log, 'set %s = %s' % (p.name, expr)):
        p.expression = expr


def catch_up(log, what='let Fusion catch up'):
    with slow(log, what):
        adsk.doEvents()


def vi(expr):
    return adsk.core.ValueInput.createByString(expr)


# The parameter test's stages, in the order they run. random runs only when asked for.
TESTS = ('ends', 'steps', 'extremes')


# The mode a design script reads from mode.txt. After a colon come parameter names and test words:
# 'check:wall,height' tests those parameters only, 'check:extremes' runs only that stage, and
# 'check:random=50,seed=7' adds 50 random sets after the other stages. Returns (mode, names, test):
# names None for every parameter, test the keywords for trials(), as b.trials(only=ONLY, **TEST).
def split_mode(mode):
    mode = mode.strip()
    if ':' not in mode:
        return mode, None, {}
    mode, rest = mode.split(':', 1)
    names, tests, test = [], [], {}
    for item in [x.strip() for x in rest.split(',') if x.strip()]:
        word, _, n = item.partition('=')
        if word == 'random':
            tests.append('random')
            test['runs'] = int(n or 20)
        elif word == 'seed':
            test['seed'] = int(n)
        elif word in TESTS:
            tests.append(word)
        else:
            names.append(item)
    if tests == ['random']:
        tests = list(TESTS) + tests
    if tests:
        test['tests'] = tuple(tests)
    return mode, names or None, test


# The parameter test's two values for a plain value, a step down and a step up: one less and one more
# for a whole-number count (never below 1), else 0.8 and 1.25 times it. A formula gets none.
def trial_values(expr):
    m = re.fullmatch(r'\s*(-?[0-9.]+)\s*([a-zA-Z]*)\s*', expr)
    if not m:
        return []
    n, unit = float(m.group(1)), m.group(2)
    if not unit and n == int(n):
        return ['%d' % v for v in (n - 1, n + 1) if v >= 1]
    if n == 0:
        return []
    return [('%g %s' % (round(n * f, 4), unit)).strip() for f in (0.8, 1.25)]


# Two sizes from the parameter test match: numbers within 1 mm3, anything else equal.
def _same_size(a, b):
    a, b = (a if isinstance(a, tuple) else (a,)), (b if isinstance(b, tuple) else (b,))
    return len(a) == len(b) and all(abs(x - y) <= 1 if isinstance(x, float) else x == y for x, y in zip(a, b))


# What differs between two Builder.bodies() lists, as plain lines: a body gone or new, a volume more than
# 1 mm3 off, a box corner more than 0.01 mm off. Like the library tests' compare (tests/upsert_harness.py).
def _body_changes(a, b):
    na, nb = ['/'.join(x[:2]) for x in a], ['/'.join(x[:2]) for x in b]
    if na != nb:
        gone, new = list(na), list(nb)
        for n in na:
            if n in new:
                gone.remove(n)
                new.remove(n)
        return ['gone: %s' % ', '.join(gone)] * bool(gone) + ['new: %s' % ', '.join(new)] * bool(new)
    out = []
    for n, x, y in zip(na, a, b):
        if abs(x[2] - y[2]) > 1:
            out.append('%s: volume %.1f mm3, was %.1f' % (n, y[2], x[2]))
        if any(abs(p - q) > 0.01 for p, q in zip(x[3], y[3])):
            out.append('%s: moved, box %s, was %s' % (n, list(y[3]), list(x[3])))
    return out


def _code_print(code):
    # Ignores line numbers, so a comment elsewhere in the file changes nothing.
    parts = [code.co_code, repr(code.co_names), repr(code.co_varnames)]
    for c in code.co_consts:
        parts.append(_code_print(c) if hasattr(c, 'co_code') else repr(_in_old_names(c)))
    return hashlib.sha1(''.join(str(x) for x in parts).encode()).hexdigest()


_PLAIN = (str, int, float, bool, type(None))


def _plain(v):
    return isinstance(v, _PLAIN) or isinstance(v, tuple) and all(_plain(i) for i in v)


def _code_names(code):
    names = set(code.co_names)
    for c in code.co_consts:
        if hasattr(c, 'co_code'):
            names |= _code_names(c)
    return names


# A function's own code, plus what it reads from outside: the values it captured, its defaults, and the
# plain values and same-file or helpers.py functions it reads by name. So a changed helper, setting or captured value
# reruns the steps that use it (C3, C4). The builder, Fusion objects, lists and dicts are left
# out: they differ from run to run without saying anything about the step.
def _fn_print(fn, home, seen):
    code = fn.__code__
    if code in seen:
        return code.co_name
    seen = seen | {code}
    parts = [_code_print(code)]
    for name, cell in zip(code.co_freevars, getattr(fn, '__closure__', None) or ()):
        try:
            parts.append(name + '=' + _outside_print(cell.cell_contents, home, seen))
        except ValueError:
            pass  # A cell not filled in yet.
    for v in getattr(fn, '__defaults__', None) or ():
        parts.append(_outside_print(v, home, seen))
    g = getattr(fn, '__globals__', None) or {}
    for name in sorted(_code_names(code)):
        if name in g:
            p = _outside_print(g[name], home, seen)
            if p:
                parts.append(name + '=' + p)
    return hashlib.sha1('|'.join(parts).encode()).hexdigest()


# While a fingerprint is taken in a design's old parameter names: new name -> old name (B5). _MET
# collects the names it met.
_BACK = {}
_MET = set()


def _old_name(m):
    _MET.add(m.group(1))
    return _BACK[m.group(1)]


def _in_old_names(v):
    if isinstance(v, str) and _BACK:
        return re.sub(r'\b(%s)\b' % '|'.join(re.escape(n) for n in _BACK), _old_name, v)
    if isinstance(v, tuple):
        return tuple(_in_old_names(i) for i in v)
    return v


def _outside_print(v, home, seen):
    if _plain(v):
        return repr(_in_old_names(v))
    # helpers.py counts as the script's own file: a changed helper reruns the steps that use it. Before,
    # only same-file functions counted, so moving a helper there changed every fingerprint
    # and an edit to it changed none.
    if hasattr(v, '__code__') and getattr(v, '__module__', None) in (home, __name__ + '.helpers'):
        return _fn_print(v, home, seen)
    return ''


def _print(x):
    if hasattr(x, '__code__'):
        return _fn_print(x, getattr(x, '__module__', None), frozenset())
    if isinstance(x, (tuple, list)):
        return '(' + ','.join(_print(i) for i in x) + ')'
    # A set prints its items in a different order each run, so it is sorted.
    if isinstance(x, (set, frozenset)):
        return '{' + ','.join(sorted(_print(i) for i in x)) + '}'
    r = repr(_in_old_names(x))
    # An object printed with its memory address would rebuild the step on every run.
    if ' at 0x' in r:
        raise ValueError('its spec holds %s, which prints differently each run. Pass its name, or a function that finds it' % r)
    return r


def fingerprint(*spec):
    return hashlib.sha1(_print(spec).encode()).hexdigest()[:16]


def _attr(entity, name):
    # Hand-made timeline items can be types with no attributes at all.
    try:
        a = entity.attributes.itemByName(GROUP, name)
    except:
        return None
    return a.value if a else None


def tag(entity, name):
    # Marks a sketch point or curve, so another step can find it after a rerun.
    entity.attributes.add(GROUP, 'tag', name)


def tagged(sketch, name):
    for group in (sketch.sketchPoints, sketch.sketchCurves):
        for q in group:
            if _attr(q, 'tag') == name:
                return q
    raise Exception('nothing tagged %s in sketch %s' % (name, sketch.name))


# A block inside a draw function that holds the sketch's solve and profiles until it ends:
#     with deferred(s):
#         ...lines, constraints, dimensions...
# 60 dimensioned rectangles drew 2.7 times faster, with the same profiles, all constrained (2026-11-18).
# A sketch step's draw always gets a new sketch, which is where the docs allow it (isComputeDeferred).
# Read nothing inside the block that needs the solve: a point's place after a dimension, profiles,
# isFullyConstrained. A report of loose points goes after it.
class deferred:
    def __init__(self, sketch):
        self.s = sketch

    def __enter__(self):
        self.s.isComputeDeferred = True
        self.s.areProfilesShown = False
        return self.s

    def __exit__(self, *a):
        self.s.isComputeDeferred = False
        self.s.areProfilesShown = True
        return False


def open_groups(tl):
    # A step inside a collapsed group has no timeline number and can't be rolled to.
    # Expanded, the timeline lists every step in order. Returns the ones it opened.
    closed = [g for g in tl.timelineGroups if g.isCollapsed]
    for g in closed:
        g.isCollapsed = False
    return closed


def close_groups(groups):
    for g in groups:
        if g.isValid:
            g.isCollapsed = True


# Closes a tab without saving. On its own so a test can make it refuse (K8): patching Fusion's
# Document class didn't reach the tab's own close.
def _close(doc):  # slow-ok: its one caller, _go_back, runs it inside slow()
    doc.close(False)


def _set_name(ent, name):
    # An occurrence takes its name from its component.
    target = ent.component if ent.objectType == adsk.fusion.Occurrence.classType() else ent
    target.name = name


def _name_of(ent):
    return ent.component.name if ent.objectType == adsk.fusion.Occurrence.classType() else ent.name


# An edge, face, axis, plane or point in a fingerprint: its name, or for one with no name (an edge, a
# face, a sketch line) its body or sketch and where it sits. The kind alone missed a pattern moved from
# one edge to another (F5).
def _axis_name(axis):
    name = getattr(axis, 'name', None)
    if name:
        return name
    tag = _attr(axis, 'tag')
    owner = getattr(axis, 'body', None) or getattr(axis, 'parentSketch', None)
    bits = [axis.objectType, getattr(owner, 'name', None), tag]
    if not tag:
        box = getattr(axis, 'boundingBox', None)
        at = getattr(axis, 'geometry', None)
        bits += [_at(p) for p in ((box.minPoint, box.maxPoint) if box else (at,) if hasattr(at, 'x') else ())]
    return ' '.join(b for b in bits if b)


def _at(p):
    # To a thousandth of a millimetre, with no "-0.0000" to tell apart from "0.0000".
    return ','.join('%.4f' % (round(v, 4) + 0.0) for v in (p.x, p.y, p.z))


# The settings Fusion can't edit in place, one fingerprint each, so a change names what changed (F1).
def _fixed_record(key, fixed):
    return ';'.join('%s=%s' % (label, fingerprint(key, v)) for label, v in fixed)


def _fixed_changed(was, now):
    # A step made before the record was kept is edited in place as before: replacing it could fail on
    # hand-made items after it, and its settings most likely did not change in the same run.
    if was is None:
        return []
    old = dict(x.split('=', 1) for x in was.split(';') if x)
    return [label for label, fp in (x.split('=', 1) for x in now.split(';') if x) if old.get(label) != fp]


def _input(x):
    # A step's input in its fingerprint: a function by its code, an entity by its name.
    return x if x is None or callable(x) else _axis_name(x)


def _get(x):
    # An entity, or a function that finds it now. A function is safer when the step it comes from can be
    # made again in the run.
    return x() if callable(x) else x


def _collection(items):
    c = adsk.core.ObjectCollection.create()
    for x in items:
        c.add(x)
    return c


# A pattern's compute option, from compute ('identical', 'optimized' or 'adjust') or the older
# adjust=True. Gives the Fusion value (None leaves Fusion's own, which is Adjust in the API), what goes
# in the spec and the fixed record. A step that names neither keeps the spec and record it had, so
# designs built before compute= are not made again. A new compute makes the feature again: Fusion
# may ignore a change to it on an existing one (fusion/rules.md rule 32).
_COMPUTE = {'identical': 'IdenticalPatternCompute', 'optimized': 'OptimizedPatternCompute', 'adjust': 'AdjustPatternCompute'}


def _compute(compute, adjust):
    compute = compute or ('adjust' if adjust else None)
    if compute is not None and compute not in _COMPUTE:
        raise ValueError("compute is %r; use 'identical', 'optimized' or 'adjust'" % (compute,))
    how = getattr(adsk.fusion.PatternComputeOptions, _COMPUTE[compute]) if compute else None
    said = ('adjust',) if compute == 'adjust' else ('compute', compute) if compute else ()
    fixed = (('adjust', compute == 'adjust'),) + ((('compute', compute),) if compute not in (None, 'adjust') else ())
    return how, said, fixed


def _token(x):
    occ = adsk.fusion.Occurrence.cast(x)
    if occ:
        # Fusion makes no token for an occurrence inside a subcomponent, so editing a pattern of one
        # failed and replaced it, and the new pattern lost track of its copies (I4).
        return 'occurrence ' + (occ.nativeObject or occ).name
    return x.entityToken


def _tokens(items):
    return sorted(_token(x) for x in items if x)


# Two entities, or two lists of them, are the same. == first: a token string can change while the
# entity stays the same, so tokens are only the fallback (the findEntityByToken docs).
def _same_entity(a, b):
    return a == b or (a is not None and b is not None and _token(a) == _token(b))


def _same_entities(a, b):
    a, b = [x for x in a if x], [x for x in b if x]
    return len(a) == len(b) and (all(x == y for x, y in zip(a, b)) or _tokens(a) == _tokens(b))


def _owner(x):
    # The component a sketch point, vertex, construction point or joint origin belongs to.
    for path in (('parentComponent',), ('component',), ('body', 'parentComponent'), ('parentSketch', 'parentComponent')):
        y = x
        for p in path:
            y = getattr(y, p, None)
        if y is not None:
            return y
    return None


_DIRECTIONS = {a: getattr(adsk.fusion.JointDirections, a.upper() + 'AxisJointDirection') for a in 'xyz'}
_MOTIONS = {'rigid': adsk.fusion.JointTypes.RigidJointType, 'revolute': adsk.fusion.JointTypes.RevoluteJointType,
            'slider': adsk.fusion.JointTypes.SliderJointType}


def _check_motion(name, motion, axis):
    if motion not in _MOTIONS:
        raise Exception('%s: motion %s, use rigid, revolute or slider' % (name, motion))
    if axis not in _DIRECTIONS:
        raise Exception('%s: axis %s, use x, y or z' % (name, axis))


def _set_motion(j, motion, axis, *at):
    # j: a joint, an as-built joint, or the input for one. at: an as-built joint's new geometry, which
    # only comes with its motion. Set alone, Fusion refuses it on a rigid one and needs it for the others.
    if motion == 'rigid':
        j.setAsRigidJointMotion()
    elif motion == 'revolute':
        j.setAsRevoluteJointMotion(_DIRECTIONS[axis], *at)
    else:
        j.setAsSliderJointMotion(_DIRECTIONS[axis], *at)


def _motion_of(j):
    m = j.jointMotion
    kind = {v: k for k, v in _MOTIONS.items()}.get(m.jointType, 'type %s' % m.jointType)
    turns, slides = adsk.fusion.RevoluteJointMotion.cast(m), adsk.fusion.SliderJointMotion.cast(m)
    d = turns.rotationAxis if turns else slides.slideDirection if slides else None
    return kind if d is None else '%s %s' % (kind, {v: k for k, v in _DIRECTIONS.items()}.get(d, d))


# A path for sweep, pipe and path_pattern. chain: Fusion adds the curves joined end to end to the ones
# given. Off for one curve of a sketch whose curves meet, like the suspension bridge's main and side cables.
def _route(feats, curves, chain):
    return feats.createPath(_collection(curves) if isinstance(curves, (list, tuple)) else curves, chain)


def timeline_items(tl):
    # Every step in order, without the groups. Leaves the groups the way they were.
    closed = open_groups(tl)
    items = [tl.item(i) for i in range(tl.count)]
    close_groups(closed)
    return items


# Fusion has no group inside a group, so a group in a component is named after it: "Frame · legs".
class group_scope:
    def __init__(self, builder, name):
        self.b = builder
        self.name = '%s · %s' % (builder.comp_names[-1], name) if builder.comp_names else name

    def __enter__(self):
        self.outer, self.b.current_group = self.b.current_group, self.name
        self.b.group_order.append(self.name)

    def __exit__(self, *args):
        self.b.current_group = self.outer


class component_scope:
    def __init__(self, builder, key, name):
        self.b, self.key, self.name = builder, key, name

    # The component's own steps, outside any group in it, go in a group named after it.
    def __enter__(self):
        self.outer_group, self.b.current_group = self.b.current_group, self.name
        self.b.group_order.append(self.name)
        self.outer, self.b.comp = self.b.comp, self.b._enter_component(self.key, self.name)
        self.b.comp_names.append(self.name)
        return self.b.comp

    def __exit__(self, *args):
        self.b.comp = self.outer
        self.b.comp_names.pop()
        self.b.current_group = self.outer_group


class Builder:
    # go_back_to: the version a failed run goes back to, when the tab isn't that version plus hand
    # changes. A clean run passes the version from before its wipe (wipe() returns it).
    def __init__(self, design, doc=None, log=None, go_back_to=None):
        self.des, self.doc = design, doc
        self.root = design.rootComponent
        self.comp = self.root  # Where the next step goes. A component() block changes it.
        self.warned_top = False
        self.tl = design.timeline
        self.log = log if log is not None else []
        self.unsaved_at_start = bool(doc and doc.isModified)  # Read first: opening groups marks a design as changed.
        self.restore_from = None
        self.go_back_to = go_back_to
        stuck = _attr(design, 'go_back_to')
        if go_back_to is None and stuck and self.unsaved_at_start:
            # The last run here could not go back (_go_back). Saving this tab would keep its half-built state.
            self.go_back_to = int(stuck)
            self.log.append('the last run here could not go back, so this tab may be half-built: a failed run goes back to version %d, the last good one, and no restore point is saved' % self.go_back_to)
        elif go_back_to is None and self.unsaved_at_start and doc.dataFile:
            # Before any change, so a run that stops at its first step still has the hand changes to go back to (F2).
            before = doc.dataFile.latestVersionNumber
            with self._slow('save a restore point'):
                saved = doc.save('Restore point before a script rerun')
            if not saved:
                raise Exception('could not save a restore point of the unsaved changes, so nothing was changed')
            self.restore_from = before
            self.log.append('restore point saved')
        self.group_states = {g.name: g.isCollapsed for g in self.tl.timelineGroups}
        self.closed_groups = open_groups(self.tl)
        if self.tl.markerPosition < self.tl.count:
            with self._slow('marker to the end'):
                self.tl.moveToEnd()  # A part whose step is rolled past can't be read, so it would look hand-made.
        self.known = {}
        self.retired = []
        for it in timeline_items(self.tl):
            key = _attr(it.entity, 'key')
            if _attr(it.entity, 'retired'):
                self.retired.append(it.entity)
            elif key:
                self.known[key] = it.entity
        self.foreign_at_start = self.foreign()
        # Hand-made steps that warn already. One that starts to warn during the run lost something the run took (F4).
        self.foreign_warned_at_start = [it.name for it in timeline_items(self.tl) if not _attr(it.entity, 'key') and it.healthState == WarningState]
        # Steps already in error. The run didn't break them, so they don't send it back (F2).
        self.errors_at_start = [it.name for it in timeline_items(self.tl) if it.healthState == ErrorState]
        self.visited = []
        self.read_files = {}  # script file -> its step keys, read ahead by precheck (A5)
        self.made = {}  # key -> how the script makes it, so a step lost in a replace can be made again
        self.lost_with = {}  # key -> the step whose delete took it, for steps the script hasn't reached yet
        self.names_later = []  # (feature, body name) for edits made with the marker before the feature
        # An "(old)" sketch left by a run that stopped: the steps built on it may still point at it, and it
        # goes at the end of this run. So its key counts as changed, and those steps pick again (D6).
        self.changed = {_attr(e, 'key') for e in self.retired if _attr(e, 'key')}
        self.prev = None
        self.prev_key = None
        self.structure_changed = False
        self.whole_again = False  # finish() cleared the go_back_to mark, so save() saves
        self.current_group = None
        self.comp_names = []
        self.group_order = []
        self.group_keys = {}
        self.counts = {'created': 0, 'updated': 0, 'replaced': 0, 'same': 0, 'removed': 0}
        self.touched = []  # (what happened, step name, why), so a log says which steps a count stands for.
        self.params_set = []
        self.params_kept = []
        self.params_seen = []
        self.profile_warned = []  # steps whose sketch has more than one profile and no profile=
        self.ranges = {}  # name -> (low, high, step) as numbers, from param(range=, step=)
        self.renamed = {}  # old name -> new name, from every was= this run
        self.names_kept = []
        self.hand_kept = []

    # Indented, so a slow call sits under the step it is for in the progress file.
    def _slow(self, what):
        return slow(self.log, '    ' + what)

    def group(self, name):
        return group_scope(self, name)

    # Steps inside the block go in this subcomponent. Nest blocks for a component inside a component.
    def component(self, key, name):
        return component_scope(self, key, name)

    def _enter_component(self, key, name):
        precheck.read_ahead(self.read_files, self.visited, self.log)  # A5: before the marker moves
        if self.des.designIntent == adsk.fusion.DesignIntentTypes.PartDesignIntentType:
            self.log.append('%s: a part design has no subcomponents, so this stays in the top component' % name)
            return self.comp
        if key in self.known:
            with self._slow('marker to the end'):
                self.tl.moveToEnd()  # A part can't be read while an earlier edit has the timeline rolled back before it.
        make = lambda: self.comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())  # slow-ok: the step's "make" line covers it
        return self.step(key, name, make).component

    def _note_top(self, ent):
        # Joints between parts belong in the top component.
        top_ok = (adsk.fusion.Occurrence.classType(), adsk.fusion.Joint.classType(), adsk.fusion.AsBuiltJoint.classType())
        if self.warned_top or self.comp.id != self.root.id or ent.objectType in top_ok:
            return
        self.warned_top = True
        self.log.append('this script builds in the top component (%s), see fusion/rules.md' % ent.name)

    def _check_component(self, ent, name):
        parent = getattr(ent, 'parentComponent', None)
        if parent and parent.id != self.comp.id:
            raise Exception('%s is in component %s, but the script now puts it in %s. Move it by hand first.' % (name, parent.name, self.comp.name))

    def body(self, key, i=0):
        bodies = self.known[key].bodies
        if i >= bodies.count:
            # Seen when a key from an older script is reused: an old step still in the timeline takes the body.
            raise Exception('step %s has no body %d now, a later step took it. If the key meant something else in an older script, give the step a new key.' % (key, i))
        return bodies.item(i)

    # Named parameters. A value changed by hand since the last run is kept. A favorite is one people
    # tune (MakerWorld's Customize shows only favorites), so it must be a plain value, not a formula.
    def param(self, name, expr, unit, comment='', favorite=False, was=None, range=None, step=None):
        # was: the parameter's old name, or a list of them (oldest first) after several renames. It is
        # renamed in place, so its value and everything that uses it carry over; Fusion rewrites the
        # expressions that name it. Keep was= in the script until every saved copy has been run once.
        # range=(low, high) and step=: the values a plain value is meant to take, '20 mm' or a bare
        # number in the parameter's unit. A count's step defaults to 1. The parameter test tries them,
        # and they are saved in the design, so the slider limits can be read back.
        precheck.read_ahead(self.read_files, self.visited, self.log)  # A5: before the parameter is made or changed
        self.params_seen.append(name)
        # It stops the run, before the parameter is made: a warning in the log was missed.
        if favorite and not re.fullmatch(r'-?[0-9.]+ *[a-z]*', expr.strip()):
            raise Exception('favorite %s = %s is a formula. A favorite must be a plain value: give its numbers their own '
                            'parameters, or make it not a favorite (fusion/rules.md)' % (name, expr))
        if range is not None:
            self.ranges[name] = ranges.check(name, expr, unit, range[0], range[1], step)
        elif step is not None:
            raise Exception('parameter %s has step= but no range=' % name)
        olds = [was] if isinstance(was, str) else list(was or [])
        for o in olds:
            self.renamed[o] = name
        attrs = self.des.attributes
        p = self.des.userParameters.itemByName(name)
        both = [o for o in olds if p is not None and self.des.userParameters.itemByName(o) is not None]
        if both:
            raise Exception('parameter %s can\'t be renamed to %s: the design already has both. Delete the one you don\'t want by hand first.' % (both[0], name))
        for o in olds if p is None else []:
            old = self.des.userParameters.itemByName(o)
            if old is None:
                continue
            old.name = name
            p = old
            for prefix in ('wrote.', 'saw.', 'range.'):
                a = attrs.itemByName(GROUP, prefix + o)
                if a:
                    attrs.add(GROUP, prefix + name, a.value)
                    a.deleteMe()  # slow-ok: an attribute
            self.params_set.append('%s renamed to %s' % (o, name))
            self.structure_changed = True
            break
        # Stored values are in the names of the run that wrote them; bring them to today's names.
        # Fusion also respaces expressions after a rename ("( a - b )"), so compare without spaces.
        wrote = attrs.itemByName(GROUP, 'wrote.' + name)
        saw = attrs.itemByName(GROUP, 'saw.' + name)
        wrote_v = self._new_names(wrote.value) if wrote else None
        saw_v = self._new_names(saw.value) if saw else None
        made = p is None
        if made:
            try:
                p = self.des.userParameters.add(name, vi(expr), unit, comment)
            except Exception as err:
                raise Exception('Fusion refused parameter %s = %s (%s): %s' % (name, expr, unit, str(err).split(' - ')[-1].strip()))
            if p is None:
                raise Exception('Fusion refused parameter %s = %s (%s); the name may be taken by a function, like floor' % (name, expr, unit))
            self.params_set.append('%s = %s, added' % (name, expr))
            kept = False
        elif (p.unit or '') != (unit or ''):
            # Fusion's API can't change a unit. A parameter nothing uses is made again in the new unit;
            # one in use is refused (B15).
            was_unit = p.unit or 'none'
            try:
                gone = p.deleteMe()  # slow-ok: Fusion deletes it only when nothing uses it
            except:
                gone = False
            if not gone:
                raise Exception('parameter %s can\'t change its unit from %s to %s: something uses it, and Fusion\'s API can\'t change a unit. '
                                'Change it by hand in the Parameters dialog, or give it a new name.' % (name, was_unit, unit or 'none'))
            try:
                p = self.des.userParameters.add(name, vi(expr), unit, comment)
            except Exception as err:
                raise Exception('Fusion refused parameter %s = %s (%s): %s' % (name, expr, unit, str(err).split(' - ')[-1].strip()))
            self.params_set.append('%s = %s, made again: its unit changed from %s' % (name, expr, was_unit))
            kept = False
        elif saw_v is not None and not _same(p.expression, saw_v):
            self.params_kept.append('%s = %s (script says %s)' % (name, p.expression, expr))
            kept = True
        elif wrote_v is None or not _same(wrote_v, expr):
            try:
                with self._slow('set %s = %s' % (name, expr)):
                    p.expression = expr
            except Exception as err:
                raise Exception('Fusion refused parameter %s = %s (%s): %s' % (name, expr, unit, str(err).split(' - ')[-1].strip()))
            self.params_set.append('%s = %s' % (name, expr))
            kept = False
        else:
            kept = False
        # Logged as set, so the run saves them (B13).
        if p.isFavorite != favorite:
            p.isFavorite = favorite
            if not made:
                self.params_set.append('%s %s' % (name, 'starred as a favorite' if favorite else 'no longer a favorite'))
        if p.comment != comment:
            p.comment = comment
            if not made:
                self.params_set.append('%s comment: %s' % (name, comment))
        if not kept:
            wrote_v, saw_v = expr, p.expression
        for a, prefix, v in ((wrote, 'wrote.', wrote_v), (saw, 'saw.', saw_v)):
            if v is not None and (a is None or a.value != v):
                attrs.add(GROUP, prefix + name, v)
        # Logged as set, so the run saves it.
        r = attrs.itemByName(GROUP, 'range.' + name)
        want = ranges.store(*self.ranges[name]) if name in self.ranges else None
        if r and want is None:
            r.deleteMe()  # slow-ok: an attribute
            self.params_set.append('%s range removed' % name)
        elif want and (r is None or r.value != want):
            attrs.add(GROUP, 'range.' + name, want)
            lo, hi, st = self.ranges[name]
            self.params_set.append('%s range %s to %s, step %s' % (name, ranges.text(lo, unit), ranges.text(hi, unit), ranges.text(st, unit)))

    def _same_but_renamed(self, key, spec, stored):
        # A spec that differs from the stored one only in the names of renamed parameters is the same
        # step: Fusion already rewrote its expressions, so nothing reruns (B5). The stored fingerprint
        # can be in any of each parameter's names, so every mix is tried, of the parameters the spec
        # names only: every mix of all 25 renames in the suspension bridge was 33 million fingerprints, a hang.
        global _BACK
        olds = {}
        for o, n in self.renamed.items():
            olds.setdefault(n, [n]).append(o)
        try:
            _BACK = {n: n for n in olds}
            _MET.clear()
            fingerprint(key, spec)
            olds = {n: v for n, v in olds.items() if n in _MET}
            for pick in itertools.product(*olds.values()):
                _BACK = {n: o for n, o in zip(olds, pick) if n != o}
                if _BACK and fingerprint(key, spec) == stored:
                    return True
        finally:
            _BACK = {}
        return False

    def _new_names(self, text):
        # Repeat, so a chain of renames (a -> b -> c) lands on the newest name.
        for _ in range(5):
            new = text
            for o, n in self.renamed.items():
                new = re.sub(r'\b%s\b' % re.escape(o), n, new)
            if new == text:
                break
            text = new
        return text

    # An edit in place runs with the marker before the feature, where its body doesn't exist yet, so the
    # new name went nowhere and the body kept its old one (C1). It's named once the marker is at the end.
    def _name_body(self, f, body_name):
        if f.bodies.count:
            f.bodies.item(0).name = body_name
        else:
            self.names_later.append((f, body_name))

    def _cursor(self):
        if self.prev is not None:
            with self._slow('marker after %s' % self.prev.name):
                self.prev.timelineObject.rollTo(False)
        else:
            with self._slow('marker to the start'):
                self.tl.moveToBeginning()

    # Fusion's own errors don't say which step they came from (C1).
    def _make(self, make, name):
        try:
            with self._slow('make %s' % name):
                return make()
        except Exception as err:
            why = str(err).split(' - ')[-1].strip()
            raise Exception(why if name in why else 'Fusion could not build %s: %s' % (name, why))

    def _mark(self, entity, key, fp, uses=(), name=None, read=None):
        entity.attributes.add(GROUP, 'key', key)
        entity.attributes.add(GROUP, 'fp', fp)
        entity.attributes.add(GROUP, 'uses', ','.join(sorted(uses)))
        if name is not None:
            entity.attributes.add(GROUP, 'name', name)  # The name the script gave it, to spot renames by hand.
        state = self._state(entity, read)
        if state is not None:
            entity.attributes.add(GROUP, 'state', state)  # The values the script built, to spot edits by hand.

    def _state(self, ent, read):
        if read is None:
            return None
        try:
            return read(ent)
        except Exception as err:
            self.log.append("could not read the values of %s (%s), so a hand edit to it won't be spotted" % (_name_of(ent), err))
            return None

    # A name given by hand stays (J1), and a new name in the script is set in place (C8). The name
    # the script gave last time tells the two apart. With no record, a different name stays and is reported.
    # " (1)" is Fusion's own: a step made while an old one of the same name was still there to delete,
    # or one named like another item in the component. On the script's last name too, so renaming it works.
    def _name_to_keep(self, ent, name):
        now, last = _name_of(ent), _attr(ent, 'name')
        if now == name or now == last or any(n and re.fullmatch(re.escape(n) + r' \(\d+\)', now) for n in (name, last)):
            return name
        return now

    def _rename(self, ent, name):
        keep = self._name_to_keep(ent, name)
        old = _name_of(ent)
        if old != keep:
            _set_name(ent, keep)
            # Fusion adds " (1)" when another item in the component has the name, a sketch and its extrude
            # say. Said once, not flagged as a change on every rerun.
            if _name_of(ent) == old:
                self.log.append('%s keeps its " (n)": another item in its component is named %s. Give the two steps different names' % (old, keep))
            else:
                self.structure_changed = True
                self.log.append('renamed %s to %s' % (old, keep))
        if keep != name:
            self.names_kept.append('%s (the script calls it %s)' % (keep, name))
        if _attr(ent, 'name') != name:
            ent.attributes.add(GROUP, 'name', name)

    # A hand edit to a value the script set (an extrude's distance, a fillet's radius) stays, like a parameter
    # changed by hand, and the run says so (J2). Records from before a parameter rename are read in new names.
    def _hand_edit(self, ent, name, read, replaced=False):
        now = self._state(ent, read)
        if now is None:
            return
        was = _attr(ent, 'state')
        if was is None:
            ent.attributes.add(GROUP, 'state', now)  # Start the record for next time.
            return
        built = self._new_names(was)
        if _same(now, built):
            if built != was:
                ent.attributes.add(GROUP, 'state', now)
        elif replaced:
            self.log.append('%s was changed by hand (%s), but the script changed this step, so its values replaced yours (%s)' % (name, now, built))
        else:
            self.hand_kept.append('%s: %s (the script built %s)' % (name, now, built))

    # One timeline step. make() creates it, update(entity) edits it in place.
    # spec is what the script says about it. uses names the steps it takes geometry
    # from: when one of those is rerun, this one picks its geometry again.
    # swap says to build a new one beside the old one, and delete the old one at the end.
    # read(entity) gives the values a person could change by hand, as text.
    # moved(ent): why the step must be made again though its spec is the same, or None. A sketch on another
    # plane is one: the plane is the script's choice at run time, not part of the spec.
    def step(self, key, name, make, update=None, spec=(), uses=(), edit_after=False, swap=False, read=None, moved=None, fixed=()):
        precheck.read_ahead(self.read_files, self.visited, self.log)  # A5: a key mistake stops the run before Fusion does work on that file
        if key in self.visited:
            raise Exception('step %s is used twice' % key)
        # A name in uses that no earlier step has is a typo or a step that comes later. Ignored, the step
        # would never pick its geometry again, so it stops the run: no silent failures.
        missing = [u for u in uses if u not in self.visited]
        if missing:
            raise Exception('step %s uses %s, but no step before it has that key' % (key, ', '.join(missing)))
        self.visited.append(key)
        try:
            fp = fingerprint(key, spec)
            fixed_now = _fixed_record(key, fixed) if fixed else None
        except ValueError as err:
            raise Exception('step %s: %s' % (key, err))
        self.made[key] = (name, make, fp, uses, self.prev_key, self.comp, read)
        progress(self.log, '  step %s' % name)
        if self.current_group:
            self.group_keys.setdefault(self.current_group, []).append(key)
        ent = self.known.get(key)
        if ent is not None and not ent.isValid:
            ent = None  # Fusion removed it along with a step it depended on.
        if ent is not None:
            self._check_component(ent, name)
            if _attr(ent, 'fp') not in (None, fp) and self._same_but_renamed(key, spec, _attr(ent, 'fp')):
                ent.attributes.add(GROUP, 'fp', fp)
        if ent is not None and ent.timelineObject.isSuppressed:
            # A choice made by hand, so it stays, but the run says so (J4).
            self.log.append('%s is suppressed, so it stays that way. Unsuppress it by hand to bring it back.' % name)
        misplaced = ent is not None and not self._in_order(ent, name)
        # A step told to take its geometry from other steps than last time picks it again. Steps marked
        # before this was stored have no record, and count as unchanged.
        was_using = _attr(ent, 'uses') if ent is not None else None
        uses_moved = was_using is not None and was_using != ','.join(sorted(uses))
        elsewhere = moved(ent) if ent is not None and moved else None
        if ent is None:
            self._cursor()
            ent = self._make(make, name)
            _set_name(ent, name)
            self._note_top(ent)
            self._mark(ent, key, fp, uses, name, read)
            self.known[key] = ent
            if key in self.lost_with:
                self.counts['replaced'] += 1
                self.touched.append(('replaced', name, 'deleted along with %s, which was made again' % self.lost_with[key]))
            else:
                self.counts['created'] += 1
                self.touched.append(('created', name, 'new'))
            self.changed.add(key)
            self.structure_changed = True
        elif _attr(ent, 'fp') is None and not misplaced and not uses_moved and not elsewhere and not any(u in self.changed for u in uses):
            self._rename(ent, name)
            self._mark(ent, key, fp, uses, read=read)  # Taken over: it's as the script says, from now on it's tracked.
            self.counts['same'] += 1
        elif _attr(ent, 'fp') != fp or misplaced or uses_moved or elsewhere or any(u in self.changed for u in uses):
            # A setting Fusion can't edit in place, or ignores, changed: the feature is made again (F1).
            stuck = _fixed_changed(_attr(ent, 'fixed'), fixed_now) if fixed else []
            why = 'out of order' if misplaced else "%s changed, which can't be edited in place" % ', '.join(stuck) if stuck else \
                'its spec changed' if _attr(ent, 'fp') != fp else \
                'it takes geometry from other steps now' if uses_moved else elsewhere or 'it uses ' + ', '.join(u for u in uses if u in self.changed)
            self.structure_changed = True
            self.changed.add(key)
            self._hand_edit(ent, name, read, replaced=True)
            keep = self._name_to_keep(ent, name)
            done = False
            if swap:
                if misplaced:
                    self._cursor()  # Its old spot is before what it now takes geometry from.
                else:
                    with self._slow('marker after %s' % ent.name):
                        ent.timelineObject.rollTo(False)
                ent.name = ent.name + ' (old)'
                ent.attributes.add(GROUP, 'retired', '1')
                self.retired.append(ent)
                ent = self._make(make, name)
                _set_name(ent, keep)
                self._mark(ent, key, fp, uses, name, read)
                self.known[key] = ent
                self.counts['updated'] += 1
                self.touched.append(('updated', name, why))
                done = True
            elif update and not misplaced and not stuck:
                try:
                    with self._slow('marker %s %s' % ('after' if edit_after else 'before', ent.name)):
                        ent.timelineObject.rollTo(not edit_after)
                    with self._slow('edit %s' % name):
                        update(ent)
                    self._rename(ent, name)
                    self._mark(ent, key, fp, uses, read=read)
                    self.counts['updated'] += 1
                    self.touched.append(('updated', name, why))
                    done = True
                except Exception as err:
                    self.log.append('could not edit %s in place, replacing it: %s' % (name, str(err).split(' - ')[-1].strip()))
            if not done:
                self._refuse_if_not_last(ent, name)
                after = self._built_after(ent)
                with self._slow('marker after %s' % ent.name):
                    ent.timelineObject.rollTo(False)
                with self._slow('delete %s, to make it again' % ent.name):
                    ent.deleteMe()
                # Fusion takes the steps built on it too. The ones the script hasn't reached yet are made
                # again when it gets there, and the log says why.
                self.lost_with.update({k: name for k, e in self.known.items() if k not in self.visited and not e.isValid and k not in self.lost_with})
                self._rebuild([k for k in after if not self.known[k].isValid], name)
                self._cursor()
                ent = self._make(make, name)
                _set_name(ent, keep)
                self._mark(ent, key, fp, uses, name, read)
                self.known[key] = ent
                self.counts['replaced'] += 1
                self.touched.append(('replaced', name, why))
        else:
            self.counts['same'] += 1
            if was_using is None:
                ent.attributes.add(GROUP, 'uses', ','.join(sorted(uses)))  # Start the record for next time.
            self._rename(ent, name)
            self._hand_edit(ent, name, read)
        if fixed and _attr(ent, 'fixed') != fixed_now:
            ent.attributes.add(GROUP, 'fixed', fixed_now)
        self.prev, self.prev_key = ent, key
        return ent

    # The steps the script already passed that sit after ent in the timeline.
    def _built_after(self, ent):
        i = ent.timelineObject.index
        return [k for k in self.visited[:-1] if k in self.known and self.known[k].isValid and self.known[k].timelineObject.index > i]

    # Deleting a step takes the steps built on it, and the ones the script already passed would be gone
    # for this run. They are made again at their spots, after the step the script has before each, so the
    # run leaves no hole (G2).
    def _rebuild(self, lost, cause, why=None):
        comp = self.comp
        for k in [k for k in self.visited if k in lost]:
            name, make, fp, uses, prev_key, self.comp, read = self.made[k]
            before = self.known.get(prev_key) if prev_key else None
            if before is not None and before.isValid:
                with self._slow('marker after %s' % before.name):
                    before.timelineObject.rollTo(False)
            else:
                with self._slow('marker to the start'):
                    self.tl.moveToBeginning()
            try:
                with self._slow('make %s again' % name):
                    ent = make()
            except Exception as err:
                self.comp = comp
                raise Exception('%s was deleted along with %s and could not be made again: %s' % (name, cause, str(err).split(' - ')[-1].strip()))
            _set_name(ent, name)
            self._mark(ent, k, fp, uses, name, read)
            self.known[k] = ent
            self.changed.add(k)
            self.counts['replaced'] += 1
            self.touched.append(('replaced', name, why or 'deleted with %s, which the script now puts after it' % cause))
        self.comp = comp
        if self.prev_key:
            self.prev = self.known[self.prev_key]

    # A feature from before this library, or one reworked in place so hand-made work after it
    # survives. The next run of the script accepts it as it is. Call this only when it matches
    # what the script says.
    def take_over(self, key, name, ent):
        # It was hand-made when the run started, so the end check would miss it as gone (J6).
        old = ent.timelineObject.name
        if old in self.foreign_at_start:
            self.foreign_at_start.remove(old)
            self.log.append('took over %s as %s' % (old, name))
        _set_name(ent, name)
        ent.attributes.add(GROUP, 'key', key)
        fp = ent.attributes.itemByName(GROUP, 'fp')
        if fp:
            fp.deleteMe()  # slow-ok: an attribute
        self.known[key] = ent
        return ent

    # The script can put a step after one that sits later in the timeline, when a design was built by an
    # older script in another order. Rolled back to its old spot, the steps it now uses don't exist yet.
    # So it moves to right after the step before it. False if Fusion won't move it.
    def _in_order(self, ent, name):
        if self.prev is None or ent.timelineObject.index > self.prev.timelineObject.index:
            return True
        if self._move_after_prev(ent, name):
            return True
        # A block the script moved as a whole: the steps built on this one that the script hasn't reached
        # yet sit in the way. Those between go first, last one first so they keep their order, and this one
        # follows (E3). Hand-made ones stay put, and if one is built on it, nothing moves.
        i, j = ent.timelineObject.index, self.prev.timelineObject.index
        ahead = [it.entity for it in timeline_items(self.tl)[i + 1:j] if self._unreached(it.entity)]
        for e in reversed(ahead):
            if not self._move_after_prev(e, e.name):
                break
        else:
            if ahead and self._move_after_prev(ent, name):
                return True
        if self.why_not:
            self.log.append('could not move %s: %s' % (name, self.why_not))
        return False

    def _unreached(self, ent):
        key = _attr(ent, 'key')
        return bool(key) and key not in self.visited and not _attr(ent, 'retired')

    def _move_after_prev(self, ent, name):
        self.why_not = None
        nxt = self.prev.timelineObject.index + 1
        # Both take the index to land before, not a timeline item; -1 is the end.
        to = nxt if nxt < self.tl.count else -1
        try:
            with self._slow('move %s after %s' % (name, self.prev.name)):
                moved = ent.timelineObject.canReorder(to) and ent.timelineObject.reorder(to)
            if moved:
                self.structure_changed = True
                self.log.append('moved %s to after %s, where the script has it' % (name, self.prev.name))
                return True
        except Exception as err:
            self.why_not = str(err).split(' - ')[-1].strip()
        if to == -1 and self._later_come_forward(ent):
            self.why_not = None
            self.structure_changed = True
            self.log.append('moved %s to after %s, where the script has it' % (name, self.prev.name))
            return True
        return False

    # Fusion won't move a step past the last one: reorder() refused every index there, while
    # canReorder() said yes (E11). So the steps after it come in front of it instead,
    # first one first so they keep their order. Only when the script already put them all before it.
    def _later_come_forward(self, ent):
        later = [it.entity for it in timeline_items(self.tl)[ent.timelineObject.index + 1:]]
        if not later or not all(_attr(e, 'key') in self.visited for e in later):
            return False
        for e in later:
            try:
                with self._slow('move %s before %s' % (e.name, ent.name)):
                    moved = e.timelineObject.reorder(ent.timelineObject.index)
                if not moved:
                    return False
            except Exception as err:
                self.why_not = str(err).split(' - ')[-1].strip()
                return False
        return True

    # A make with an .offset() (the offset expression) puts it in the spec and edits the plane in
    # place when it changes. Before, a changed offset left the old plane standing.
    def plane(self, key, name, make, spec=(), uses=()):
        off = getattr(make, 'offset', None)
        if off is None:
            return self.step(key, name, make, spec=(spec, make), uses=uses)

        def update(ent):  # slow-ok: step() logs it as "edit"
            ent.definition.offset.expression = off()
        return self.step(key, name, make, update=update, spec=(spec, off(), make), uses=uses,
                         read=lambda ent: ent.definition.offset.expression)

    # Deleting a feature can take everything built on it, and Fusion gives no list of what.
    # Read with the marker at the end: a part whose step is rolled past can't be read, so the
    # script's own parts looked hand-made and blocked the replace.
    def _refuse_if_not_last(self, ent, name):
        with self._slow('marker to the end'):
            self.tl.moveToEnd()
        after = [it.name for it in timeline_items(self.tl)[ent.timelineObject.index + 1:] if not _attr(it.entity, 'key')]
        if after:
            raise Exception('%s can only be replaced by deleting it, which could take this with it: %s' % (name, ', '.join(after)))

    # A sketch past the marker can't give its plane, which read as "its plane is gone" and redrew it
    # after any replace before it (F40). So the marker goes to it and it's read again; None if still not.
    def _plane_of(self, s):
        try:
            return s.referencePlane
        except RuntimeError:
            if not s.timelineObject.isRolledBack:
                return None
        with self._slow('marker after %s' % s.name):
            s.timelineObject.rollTo(False)
        try:
            return s.referencePlane
        except RuntimeError:
            return None

    # Sketches are redrawn, never matched piece by piece. Clearing the same sketch loses the
    # profile its extrude points at, and Fusion then refuses a new one. So the redraw is a new
    # sketch right after the old one, and the old one goes once the extrude has moved over.
    def sketch(self, key, name, plane, draw, spec=(), uses=()):
        def make():  # slow-ok: the step's "make" line covers it
            s = self.comp.sketches.add(plane())
            s.name = name
            draw(s)
            return s

        # A sketch found again in a design with components gives its plane as seen from the top, so both
        # sides are read in their own component. Tried on construction planes only; a sketch on a face
        # may read as moved after the face is remade.
        def moved(s):
            now = self._plane_of(s)
            if now is None:
                return 'its plane is gone'  # A sketch whose plane was made again this run (E5).
            want = plane()
            now, want = (getattr(x, 'nativeObject', None) or x for x in (now, want))
            if now is None or want is None or now == want or _token(now) == _token(want):
                return None
            return 'it is on another plane now'

        return self.step(key, name, make, spec=(draw, spec), uses=uses, swap=True, moved=moved)

    # profile(sketch) picks the profile, or a collection of them, when the first one isn't it.
    # taper: an angle expression, one-sided extrudes only; Fusion's sign (positive grows outward or in) is
    # checked by the caller on the finished shape.
    # thin= makes a thin wall along the profile's outline instead of a solid: a thickness, or
    # (thickness, 'side1' | 'center' | 'side2') to say which side of the outline the wall goes.
    def extrude(self, key, name, sketch, operation, symmetric=None, distance=None, participants=None, body_name=None, profile=None, taper=None,
                thin=None, spec=(), uses=()):
        ex = self.comp.features.extrudeFeatures
        walls = {'side1': adsk.fusion.ThinExtrudeWallLocation.Side1, 'center': adsk.fusion.ThinExtrudeWallLocation.Center,
                 'side2': adsk.fusion.ThinExtrudeWallLocation.Side2}
        wall, wall_at = (thin if isinstance(thin, tuple) else (thin, 'side1')) if thin else (None, None)
        if thin and wall_at not in walls:
            raise Exception("%s: thin wall side %r, use 'side1', 'center' or 'side2'" % (name, wall_at))
        skey = _attr(sketch, 'key')

        # A step rebuilt later in the run (G2) makes it again, when its sketch may be a new one.
        def sk():
            s = self.known.get(skey) if skey else None
            return s if s is not None and s.isValid else sketch
        pick = lambda: profile(sk()) if profile else self._first_profile(sk(), name)

        def extent(target):
            if symmetric:
                # The taper too, as an edit sets it: before, a fresh build left it out (F1).
                target.setSymmetricExtent(vi(symmetric), True, vi(taper or '0 deg'))
            elif taper:
                target.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(vi(distance)), adsk.fusion.ExtentDirections.PositiveExtentDirection, vi(taper))
            else:
                target.setDistanceExtent(False, vi(distance))

        # Fusion drops "full length" from a symmetric extrude that is given its bodies: it then goes the
        # distance each way, twice as thick as asked. Seen on every Cut and Join with participants, never on
        # New. So it is set again on the finished feature, and checked.
        def full_length(f):
            if not symmetric:
                return
            d = adsk.fusion.SymmetricExtentDefinition.cast(f.extentOne)
            if d and not d.isFullLength:
                d.isFullLength = True
                d = adsk.fusion.SymmetricExtentDefinition.cast(f.extentOne)
            if not d or not d.isFullLength:
                raise Exception('%s: Fusion would not keep the symmetric extent full length' % name)

        def make():
            ei = ex.createInput(pick(), operation)
            extent(ei)
            if thin:
                ei.setThinExtrude(walls[wall_at], vi(wall))
            if participants:
                ei.participantBodies = participants()
            f = ex.add(ei)
            full_length(f)
            if body_name:
                f.bodies.item(0).name = body_name
            return f

        def update(f):  # slow-ok: step() logs it as "edit"
            f.profile = pick()
            # Fusion can turn a Join that touched nothing into a New body, and an update never set it back:
            # rails stayed loose after the base they sat on moved under them.
            if f.operation != operation:
                f.operation = operation
            # A finished extrude takes these differently from its input, and wants the taper.
            none = vi(taper or '0 deg')
            if symmetric:
                f.setSymmetricExtent(vi(symmetric), True, none)
            else:
                f.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(vi(distance)), adsk.fusion.ExtentDirections.PositiveExtentDirection, none)
            full_length(f)
            if thin and f.isThinExtrude:
                f.thinExtrudeWallLocationOne = walls[wall_at]
                f.thinExtrudeWallThicknessOne.expression = wall
            elif thin:
                f.setThinExtrude(walls[wall_at], vi(wall))
            elif f.isThinExtrude:
                f.isThinExtrude = False
            # An edit in place fights itself: setting the extent can leave a cut working on every body (the
            # bridge's leg bar cut, meant for its helper sheet only, carved the frame's left leg), and setting
            # the bodies drops full length (every cut and join came out twice as thick). So the
            # bodies are set, full length set again, and both read back; a mismatch replaces the step.
            if participants:
                want = participants()
                f.participantBodies = want
                full_length(f)
                got, asked = sorted(b.name for b in f.participantBodies), sorted(b.name for b in want)
                if got != asked:
                    raise Exception('%s cuts %s, not only %s' % (name, ', '.join(got), ', '.join(asked)))
            if body_name:
                self._name_body(f, body_name)

        # Only scripts that pick a profile get it in the fingerprint, so older designs don't rerun. The
        # bodies it works on and the body's name count too: before, a change to them did nothing (C1).
        said = (symmetric, distance, operation, spec) + ((profile,) if profile else ())
        said += ((participants,) if participants else ()) + ((body_name,) if body_name else ())
        said += (('taper', taper),) if taper else ()
        said += (('thin', thin),) if thin else ()
        # Extrudes made before the full-length fix are stale: this mark makes them update once.
        said += ('full length',) if symmetric and participants else ()
        # Extrudes edited before the read-back above may cut extra bodies: this mark made them update once.
        # Symmetric ones then lost full length, so theirs is new and they update once more. One-sided ones
        # keep their mark: updating them again knocks over the combines after them.
        said += (('bodies, then full length',) if symmetric else ('only its bodies',)) if participants else ()
        # The distance only: Fusion can turn a Join into a New body by itself, so the operation says
        # nothing about hand edits.
        def read(f):
            d = adsk.fusion.SymmetricExtentDefinition.cast(f.extentOne) if symmetric else adsk.fusion.DistanceExtentDefinition.cast(f.extentOne)
            if f.isThinExtrude:
                side = [k for k, w in walls.items() if w == f.thinExtrudeWallLocationOne]
                return ','.join([d.distance.expression, f.thinExtrudeWallThicknessOne.expression] + side)
            return d.distance.expression

        # A step that stops naming its bodies would keep cutting the old ones (F1).
        return self.step(key, name, make, update, spec=said, uses=tuple(uses) + (skey,), read=read,
                         fixed=(('participants', bool(participants)),))

    def combine(self, key, name, target, tools, operation, body_name=None, spec=(), uses=()):
        cf = self.comp.features.combineFeatures

        def as_collection():
            c = adsk.core.ObjectCollection.create()
            for x in tools():
                c.add(x)
            return c

        def make():
            ci = cf.createInput(target(), as_collection())
            ci.operation = operation
            f = cf.add(ci)
            if body_name:
                f.bodies.item(0).name = body_name
            return f

        # Only what changed is set: Fusion can refuse to take the same bodies again (InternalValidationError),
        # and a refused edit means a replace, which takes later steps with it.
        def update(f):
            t = target()
            if f.targetBody is None or f.targetBody.entityToken != t.entityToken:
                f.targetBody = t
            new = as_collection()
            old = f.toolBodies
            if sorted(x.entityToken for x in new) != sorted(old.item(i).entityToken for i in range(old.count) if old.item(i)):
                f.toolBodies = new
            if body_name:
                self._name_body(f, body_name)

        return self.step(key, name, make, update, spec=(operation, target, tools, body_name, spec), uses=uses,
                         fixed=(('operation', operation),))

    # Each set is (edges, radius) for a constant radius, (edges, 'chord', length) for a chord length, or
    # (edges, 'variable', start, end) for a radius that changes along the edge. A variable set can add
    # radii part way along: (edges, 'variable', start, end, ((position, radius), ...)), position from 0
    # to 1. A variable set takes one edge or a chain of tangent edges, in order.
    def fillet(self, key, name, sets, spec=(), uses=()):
        ff = self.comp.features.filletFeatures
        kinds = {'constant': adsk.fusion.ConstantRadiusFilletEdgeSet,
                 'chord': adsk.fusion.ChordLengthFilletEdgeSet,
                 'variable': adsk.fusion.VariableRadiusFilletEdgeSet}

        # A mid point's position must be a number: Fusion refuses a string there ("Value does not
        # contain a real").
        def at(position):
            return adsk.core.ValueInput.createByReal(float(position))

        # (edges, kind, plain values, mid points)
        def split(s):
            if len(s) == 2:
                return s[0], 'constant', [s[1]], ()
            if s[1] == 'chord' and len(s) == 3:
                return s[0], 'chord', [s[2]], ()
            if s[1] == 'variable' and len(s) in (4, 5):
                return s[0], 'variable', [s[2], s[3]], tuple(s[4]) if len(s) == 5 else ()
            raise Exception("fillet set %r: use (edges, r), (edges, 'chord', length) or (edges, 'variable', start, end[, mids])" % (s[1:],))

        def add_input(fi, s):
            edges, kind, vals, mids = split(s)
            if kind == 'constant':
                fi.edgeSetInputs.addConstantRadiusEdgeSet(edges, vi(vals[0]), False)
            elif kind == 'chord':
                fi.edgeSetInputs.addChordLengthEdgeSet(edges, vi(vals[0]), False)
            else:
                es = fi.edgeSetInputs.addVariableRadiusEdgeSet(edges, vi(vals[0]), vi(vals[1]), False)
                if mids:
                    es.setMidRadii([vi(r) for _, r in mids], [at(p) for p, _ in mids])

        def add_set(f, s):
            edges, kind, vals, mids = split(s)
            if kind == 'constant':
                f.edgeSets.addConstantRadiusEdgeSet(edges, vi(vals[0]), False)
            elif kind == 'chord':
                f.edgeSets.addChordLengthEdgeSet(edges, vi(vals[0]), False)
            else:
                f.edgeSets.addVariableRadiusEdgeSet(edges, vi(vals[0]), vi(vals[1]), [at(p) for p, _ in mids],
                                                    [vi(r) for _, r in mids], False)

        # The kind of a set, its plain parameters, and its mid points as (position, radius) parameters.
        def params(es):
            for kind, cls in kinds.items():
                one = cls.cast(es)
                if not one:
                    continue
                if kind == 'constant':
                    return kind, [one.radius], []
                if kind == 'chord':
                    return kind, [one.chordLength], []
                mp, mr = one.midPositions, one.midRadii
                return kind, [one.startRadius, one.endRadius], [(mp.item(j), mr.item(j)) for j in range(mp.count)]
            raise Exception('fillet edge set of an unknown kind')

        def make():
            fi = ff.createInput()
            for s in sets():
                add_input(fi, s)
            return ff.add(fi)

        # A set that changes kind can't be edited, so the step is replaced. G4: a fillet with more than
        # one set fails here after its body is redrawn.
        def update(f):  # slow-ok: step() logs it as "edit"
            count = len(sets())
            for i in range(count):
                s = sets()[i]
                if i < f.edgeSets.count:
                    edges, kind, vals, mids = split(s)
                    had = params(f.edgeSets.item(i))[0]
                    if had != kind:
                        raise Exception('set %d was %s, now %s' % (i + 1, had, kind))
                    kinds[kind].cast(f.edgeSets.item(i)).edges = edges
                    # New edges remake the set's parameters, so they are read after (G4).
                    es = f.edgeSets.item(i)
                    one = kinds[kind].cast(es)
                    had, ps, had_mids = params(es)
                    for p, v in zip(ps, vals):
                        p.expression = v
                    if len(had_mids) == len(mids):
                        for (hp, hr), (p, r) in zip(had_mids, mids):
                            hp.expression = p
                            hr.expression = r
                    else:
                        for _ in had_mids:
                            one.deleteMidPosition(0)
                        for p, r in mids:
                            one.addMidPosition(at(p), vi(r))
                else:
                    add_set(f, s)
            while f.edgeSets.count > count:
                f.edgeSets.item(f.edgeSets.count - 1).deleteMe()
            if f.edgeSets.count != count:
                raise Exception('%d edge sets, not %d' % (f.edgeSets.count, count))

        def read(f):
            out = []
            for i in range(f.edgeSets.count):
                kind, ps, mids = params(f.edgeSets.item(i))
                out.append(','.join([p.expression for p in ps] + ['%s@%s' % (r.expression, p.expression) for p, r in mids]))
            return ';'.join(out)

        return self.step(key, name, make, update, spec=(sets, spec), uses=uses, read=read)

    # Each set is (edges, distance) for an equal-distance chamfer, (edges, 'two', d1, d2) for two
    # distances, or (edges, 'angle', distance, angle) for a distance and an angle.
    def chamfer(self, key, name, sets, spec=(), uses=()):
        cf = self.comp.features.chamferFeatures
        kinds = {'equal': adsk.fusion.EqualDistanceChamferEdgeSet,
                 'two': adsk.fusion.TwoDistancesChamferEdgeSet,
                 'angle': adsk.fusion.DistanceAndAngleChamferEdgeSet}

        def split(s):
            if len(s) == 2:
                return s[0], 'equal', [s[1]]
            if s[1] not in ('two', 'angle') or len(s) != 4:
                raise Exception("chamfer set %r: use (edges, d), (edges, 'two', d1, d2) or (edges, 'angle', d, angle)" % (s[1:],))
            return s[0], s[1], list(s[2:])

        def add(edge_sets, s):
            edges, kind, vals = split(s)
            if kind == 'equal':
                edge_sets.addEqualDistanceChamferEdgeSet(edges, vi(vals[0]), False)
            elif kind == 'two':
                edge_sets.addTwoDistancesChamferEdgeSet(edges, vi(vals[0]), vi(vals[1]), False, False)
            else:
                edge_sets.addDistanceAndAngleChamferEdgeSet(edges, vi(vals[0]), vi(vals[1]), False, False)

        # The parameters of each kind, in the order its set gives them.
        def params(es):
            for kind, cls in kinds.items():
                one = cls.cast(es)
                if one:
                    if kind == 'equal':
                        return kind, [one.distance]
                    if kind == 'two':
                        return kind, [one.distanceOne, one.distanceTwo]
                    return kind, [one.distance, one.angle]
            raise Exception('chamfer edge set of an unknown kind')

        def make():
            ci = cf.createInput2()
            for s in sets():
                add(ci.chamferEdgeSets, s)
            return cf.add(ci)

        # Same as a fillet's sets (G4). A set that changes kind can't be edited, so the step is
        # replaced.
        def update(f):  # slow-ok: step() logs it as "edit"
            count = len(sets())
            for i in range(count):
                s = sets()[i]
                if i < f.edgeSets.count:
                    edges, kind, vals = split(s)
                    had = params(f.edgeSets.item(i))[0]
                    if had != kind:
                        raise Exception('set %d was %s, now %s' % (i + 1, had, kind))
                    kinds[kind].cast(f.edgeSets.item(i)).edges = edges
                    # New edges remake the set's parameters, so they are read after (G4).
                    for p, v in zip(params(f.edgeSets.item(i))[1], vals):
                        p.expression = v
                else:
                    add(f.edgeSets, s)
            while f.edgeSets.count > count:
                f.edgeSets.item(f.edgeSets.count - 1).deleteMe()
            if f.edgeSets.count != count:
                raise Exception('%d edge sets, not %d' % (f.edgeSets.count, count))

        def read(f):
            return ';'.join(','.join(p.expression for p in params(f.edgeSets.item(i))[1]) for i in range(f.edgeSets.count))

        return self.step(key, name, make, update, spec=(sets, spec), uses=uses, read=read)

    # A solid with no history, copied from elsewhere. make_body() returns a temporary body.
    def base_body(self, key, name, make_body, spec=(), body_name=None):
        def make():  # slow-ok: the step's "make" line covers it
            base = self.comp.features.baseFeatures.add()
            base.startEdit()
            self.comp.bRepBodies.add(make_body(), base)
            base.finishEdit()
            if body_name:
                base.bodies.item(0).name = body_name
            return base

        return self.step(key, name, make, spec=(make_body, spec) + ((body_name,) if body_name else ()))

    def move(self, key, name, bodies, x, y, z, spec=(), uses=()):
        mf = self.comp.features.moveFeatures

        def make():
            mi = mf.createInput2(_collection(bodies()))
            mi.defineAsTranslateXYZ(vi(x), vi(y), vi(z), True)
            return mf.add(mi)

        # Edited in place, like the rest (approved). Before, every change replaced it.
        def update(f):
            want = bodies()
            have = f.inputEntities
            if not _same_entities(want, [have.item(i) for i in range(have.count)]):
                f.inputEntities = _collection(want)
            f.redefineAsTranslateXYZ(vi(x), vi(y), vi(z), True)

        def read(f):
            d = adsk.fusion.MoveFeatureTranslateXYZDefinition.cast(f.definition)
            return '%s;%s;%s' % (d.xDistance.expression, d.yDistance.expression, d.zDistance.expression)

        return self.step(key, name, make, update, spec=(x, y, z, bodies, spec), uses=uses, read=read)

    # Turns bodies by angle (an expression) about axis, editable like move.
    def turn(self, key, name, bodies, axis, angle, spec=(), uses=()):
        mf = self.comp.features.moveFeatures
        comp = self.comp

        # In a sub-component Fusion called the component's own axis "Invalid entity", so
        # this tries it as seen from the top component too, once per place the component sits.
        def axes():
            yield axis
            if comp.id != self.root.id:
                occs = self.root.allOccurrencesByComponent(comp)
                for i in range(occs.count):
                    yield axis.createForAssemblyContext(occs.item(i))

        def first_that_works(use):
            err = None
            for n, a in enumerate(axes()):
                try:
                    result = use(a)
                    if n:
                        self.log.append('%s: turned about the axis as seen from the top component' % name)
                    return result
                except RuntimeError as e:
                    err = err or e
            raise err

        def make():
            def use(a):
                mi = mf.createInput2(_collection(bodies()))
                mi.defineAsRotate(a, vi(angle))
                return mf.add(mi)
            return first_that_works(use)

        def update(f):
            want = bodies()
            have = f.inputEntities
            if not _same_entities(want, [have.item(i) for i in range(have.count)]):
                f.inputEntities = _collection(want)
            first_that_works(lambda a: f.redefineAsRotate(a, vi(angle)))

        def read(f):
            return adsk.fusion.MoveFeatureRotateDefinition.cast(f.definition).angle.expression

        return self.step(key, name, make, update, spec=(_axis_name(axis), angle, bodies, spec), uses=uses, read=read)

    # A copy of a body, here in this component, as a step of its own. Fusion makes the copy again from the
    # source on every compute, so a later change to the source reaches it: tuning the base part
    # carries over to its copies.
    def copy(self, key, name, body, body_name=None, spec=(), uses=()):
        def make():
            f = self.comp.features.copyPasteBodies.add(body())
            if body_name:
                f.bodies.item(0).name = body_name
            return f

        return self.step(key, name, make, spec=(body, spec) + ((body_name,) if body_name else ()), uses=uses)

    # bodies can also give features. compute: 'identical' repeats the first copy's result, for copies
    # that all land on the part the same way; 'optimized' repeats faces only and can fail on joins and
    # other contact with faces it didn't copy; 'adjust' (or adjust=True) works each copy out on its own,
    # for copies that land differently (one runs off an edge, hits a hole or joins another body). In
    # Autodesk's 3x3 pattern of a join, Optimized made 3 columns and Identical left 8 of 9 as separate
    # bodies. fusion/rules.md rule 32.
    def rect_pattern(self, key, name, bodies, axis1, n1, d1, axis2, n2, d2, adjust=False, compute=None, spec=(), uses=()):
        rp = self.comp.features.rectangularPatternFeatures
        how, how_said, how_fixed = _compute(compute, adjust)

        def as_collection():
            c = adsk.core.ObjectCollection.create()
            for b in bodies():
                c.add(b)
            return c

        def make():
            ri = rp.createInput(as_collection(), axis1, vi(n1), vi(d1), adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
            ri.setDirectionTwo(axis2, vi(n2), vi(d2))
            if how is not None:
                ri.patternComputeOption = how
            return rp.add(ri)

        def update(f):  # slow-ok: step() logs it as "edit"
            want = as_collection()
            have = f.inputEntities
            if not _same_entities([want.item(i) for i in range(want.count)], [have.item(i) for i in range(have.count)]):
                f.inputEntities = want
            if f.directionOneEntity is None or f.directionOneEntity.entityToken != axis1.entityToken:
                f.directionOneEntity = axis1
            if f.directionTwoEntity is None or f.directionTwoEntity.entityToken != axis2.entityToken:
                f.directionTwoEntity = axis2
            f.quantityOne.expression, f.distanceOne.expression = n1, d1
            f.quantityTwo.expression, f.distanceTwo.expression = n2, d2
            if how is not None:
                f.patternComputeOption = how

        def read(f):
            return '%s;%s;%s;%s' % (f.quantityOne.expression, f.distanceOne.expression, f.quantityTwo.expression, f.distanceTwo.expression)

        # The bodies and axes count too: before, a change to them did nothing (C1).
        said = (n1, d1, n2, d2, bodies, _axis_name(axis1), _axis_name(axis2), spec) + how_said
        return self.step(key, name, make, update, spec=said, uses=uses, read=read, fixed=how_fixed)

    # ---- Construction geometry. Each follows what it is built on; an edit sets it again. ----

    # A plane parallel to base, offset by an expression. With along=0, 1 or 2 (model X, Y, Z) the offset
    # is measured that way, whichever way base faces (its normal can point either way).
    def offset_plane(self, key, name, base, offset, along=None, spec=(), uses=()):
        comp = self.comp

        def off():
            if along is None:
                return offset
            n = _get(base).geometry.normal
            return offset if (n.x, n.y, n.z)[along] > 0 else '-(%s)' % offset

        def make():  # slow-ok: the step's "make" line covers it
            pi = comp.constructionPlanes.createInput()
            pi.setByOffset(_get(base), vi(off()))
            return comp.constructionPlanes.add(pi)

        # A new base can't be set on a finished plane in a way that was tested, so that replaces it.
        def update(ent):  # slow-ok: step() logs it as "edit"
            if not _same_entity(ent.definition.planarEntity, _get(base)):
                raise Exception('its base plane changed')
            ent.definition.offset.expression = off()

        return self.step(key, name, make, update, spec=(_axis_name(_get(base)), offset, along, spec), uses=uses,
                         read=lambda ent: ent.definition.offset.expression)

    # A plane through line (an edge, sketch line or axis), turned angle from plane.
    def angled_plane(self, key, name, line, angle, plane, spec=(), uses=()):
        comp = self.comp

        def make():  # slow-ok: the step's "make" line covers it
            pi = comp.constructionPlanes.createInput()
            pi.setByAngle(_get(line), vi(angle), _get(plane))
            return comp.constructionPlanes.add(pi)

        def update(ent):  # slow-ok: step() logs it as "edit"
            d = ent.definition
            if not _same_entity(d.linearEntity, _get(line)) or not _same_entity(d.planarEntity, _get(plane)):
                raise Exception('its line or plane changed')
            d.angle.expression = angle

        return self.step(key, name, make, update, spec=(_axis_name(_get(line)), angle, _axis_name(_get(plane)), spec), uses=uses,
                         read=lambda ent: ent.definition.angle.expression)

    # The plane halfway between two planes or flat faces.
    def mid_plane(self, key, name, a, b, spec=(), uses=()):
        comp = self.comp

        def make():  # slow-ok: the step's "make" line covers it
            pi = comp.constructionPlanes.createInput()
            pi.setByTwoPlanes(_get(a), _get(b))
            return comp.constructionPlanes.add(pi)

        def update(ent):  # slow-ok: step() logs it as "edit"
            ent.definition.redefine(_get(a), _get(b))

        return self.step(key, name, make, update, spec=(_axis_name(_get(a)), _axis_name(_get(b)), spec), uses=uses)

    # A construction axis. how: 'two_planes' (where a and b meet), 'line' (along an edge or sketch line a),
    # 'two_points' (a to b), 'normal' (square to face a, through point b).
    def axis(self, key, name, how, a, b=None, spec=(), uses=()):
        comp = self.comp
        by = {'two_planes': 'setByTwoPlanes', 'line': 'setByEdge', 'two_points': 'setByTwoPoints', 'normal': 'setByNormalToFaceAtPoint'}[how]
        args = lambda: [_get(x) for x in (a, b) if x is not None]

        def make():  # slow-ok: the step's "make" line covers it
            ai = comp.constructionAxes.createInput()
            getattr(ai, by)(*args())
            return comp.constructionAxes.add(ai)

        def update(ent):  # slow-ok: step() logs it as "edit"
            ent.definition.redefine(*args())

        return self.step(key, name, make, update, spec=(how, _input(a), _input(b), spec), uses=uses)

    # A construction point. how: 'two_lines' (where a and b cross), 'center' (of circle or sphere a),
    # 'point' (on sketch point or vertex a).
    def point(self, key, name, how, a, b=None, spec=(), uses=()):
        comp = self.comp
        by = {'two_lines': 'setByTwoEdges', 'center': 'setByCenter', 'point': 'setByPoint'}[how]
        args = lambda: [_get(x) for x in (a, b) if x is not None]

        def make():  # slow-ok: the step's "make" line covers it
            pi = comp.constructionPoints.createInput()
            getattr(pi, by)(*args())
            return comp.constructionPoints.add(pi)

        def update(ent):  # slow-ok: step() logs it as "edit"
            ent.definition.redefine(*args())

        return self.step(key, name, make, update, spec=(how, _input(a), _input(b), spec), uses=uses)

    # ---- Features from a sketch. The sketch's key joins uses, as for extrude. ----

    def _sketch_of(self, sketch):
        # The sketch now: a step rebuilt later in the run (G2) makes it again, when its sketch may be new.
        skey = _attr(sketch, 'key')

        def sk():
            s = self.known.get(skey) if skey else None
            return s if s is not None and s.isValid else sketch
        return sk, ((skey,) if skey else ())

    # profile turned about axis. angle: a full turn by default; symmetric splits it both ways.
    def revolve(self, key, name, sketch, axis, operation, angle='360 deg', symmetric=False, participants=None,
                body_name=None, profile=None, spec=(), uses=()):
        rf = self.comp.features.revolveFeatures
        sk, skey = self._sketch_of(sketch)
        pick = lambda: profile(sk()) if profile else self._first_profile(sk(), name)

        def make():
            ri = rf.createInput(pick(), _get(axis), operation)
            ri.setAngleExtent(symmetric, vi(angle))
            if participants:
                ri.participantBodies = participants()
            f = rf.add(ri)
            if body_name:
                f.bodies.item(0).name = body_name
            return f

        def update(f):  # slow-ok: step() logs it as "edit"
            f.profile = pick()
            f.axis = _get(axis)
            if f.operation != operation:
                f.operation = operation
            f.setAngleExtent(symmetric, vi(angle))
            if participants:
                f.participantBodies = participants()
            if body_name:
                self._name_body(f, body_name)

        said = (_axis_name(_get(axis)), operation, angle, symmetric, profile, participants, body_name, spec)
        return self.step(key, name, make, update, spec=said, uses=tuple(uses) + skey, fixed=(('participants', bool(participants)),),
                         read=lambda f: adsk.fusion.AngleExtentDefinition.cast(f.extentDefinition).angle.expression)

    # profile swept along path(): a curve or a list of them, from any sketch (chain: see _route).
    def sweep(self, key, name, sketch, path, operation, participants=None, body_name=None, profile=None, chain=True, spec=(), uses=()):
        sf = self.comp.features.sweepFeatures
        feats = self.comp.features
        sk, skey = self._sketch_of(sketch)
        pick = lambda: profile(sk()) if profile else self._first_profile(sk(), name)
        route = lambda: _route(feats, path(), chain)

        def make():
            si = sf.createInput(pick(), route(), operation)
            if participants:
                si.participantBodies = participants()
            f = sf.add(si)
            if body_name:
                f.bodies.item(0).name = body_name
            return f

        def update(f):  # slow-ok: step() logs it as "edit"
            f.profile = pick()
            f.path = route()
            if f.operation != operation:
                f.operation = operation
            if participants:
                f.participantBodies = participants()
            if body_name:
                self._name_body(f, body_name)

        return self.step(key, name, make, update, spec=(operation, path, chain, profile, participants, body_name, spec), uses=tuple(uses) + skey,
                         fixed=(('participants', bool(participants)),))

    # A round bar along path() (a curve or a list, chain: see _route), size across. hollow: the wall, for a tube.
    def pipe(self, key, name, path, size, operation, hollow=None, participants=None, body_name=None, chain=True, spec=(), uses=()):
        pf = self.comp.features.pipeFeatures
        feats = self.comp.features
        route = lambda: _route(feats, path(), chain)

        def make():
            pi = pf.createInput(route(), operation)
            pi.sectionSize = vi(size)
            if hollow:
                pi.isHollow = True
                pi.sectionThickness = vi(hollow)
            if participants:
                pi.participantBodies = participants()
            f = pf.add(pi)
            if body_name:
                f.bodies.item(0).name = body_name
            return f

        def update(f):  # slow-ok: step() logs it as "edit"
            f.path = route()
            f.sectionSize.expression = size
            if hollow:
                f.sectionThickness.expression = hollow
            if participants:
                f.participantBodies = participants()
            if body_name:
                self._name_body(f, body_name)

        return self.step(key, name, make, update, spec=(size, operation, path, chain, hollow, participants, body_name, spec), uses=uses,
                         read=lambda f: f.sectionSize.expression,
                         fixed=(('operation', operation), ('hollow', bool(hollow)), ('participants', bool(participants))))

    # A solid through sections() (profiles, or sketch points at the ends), in order. A new section edits it in
    # place; only a change in the number of sections replaces it.
    def loft(self, key, name, sections, operation, participants=None, body_name=None, spec=(), uses=()):
        lf = self.comp.features.loftFeatures

        def make():  # slow-ok: the step's "make" line covers it
            li = lf.createInput(operation)
            for s in sections():
                li.loftSections.add(s)
            if participants:
                li.participantBodies = participants()
            f = lf.add(li)
            if body_name:
                f.bodies.item(0).name = body_name
            return f

        # Points each section at its profile now, with the marker before the loft. A loft with a new
        # number of sections is replaced.
        def update(f):  # slow-ok: step() logs it as "edit"
            want = sections()
            if f.loftSections.count != len(want):
                raise Exception('%d sections, not %d' % (f.loftSections.count, len(want)))
            for i, s in enumerate(want):
                f.loftSections.item(i).entity = s
            if participants:
                f.participantBodies = participants()
            if body_name:
                self._name_body(f, body_name)

        return self.step(key, name, make, update, spec=(operation, sections, participants, body_name, spec), uses=uses,
                         fixed=(('participants', bool(participants)),))

    # Holes at sketch points: points() gives them. kind: 'simple', or 'counterbore' with (diameter, depth)
    # of the wider part, or 'countersink' with (diameter, angle). depth: an expression, or None for through all.
    def hole(self, key, name, points, diameter, depth=None, kind='simple', head=None, spec=(), uses=()):
        hf = self.comp.features.holeFeatures

        def make():
            if kind == 'counterbore':
                hi = hf.createCounterboreInput(vi(diameter), vi(head[0]), vi(head[1]))
            elif kind == 'countersink':
                hi = hf.createCountersinkInput(vi(diameter), vi(head[0]), vi(head[1]))
            else:
                hi = hf.createSimpleInput(vi(diameter))
            hi.setPositionBySketchPoints(_collection(points()))
            if depth:
                hi.setDistanceExtent(vi(depth))
            else:
                hi.setAllExtent(adsk.fusion.ExtentDirections.PositiveExtentDirection)
            return hf.add(hi)

        # Points and sizes are set again. Where Fusion can't move a finished hole, it is replaced.
        def update(f):  # slow-ok: step() logs it as "edit"
            if not hasattr(f, 'setPositionBySketchPoints'):
                raise Exception('Fusion cannot move a finished hole')
            f.setPositionBySketchPoints(_collection(points()))
            f.holeDiameter.expression = diameter
            if kind == 'counterbore':
                f.counterboreDiameter.expression, f.counterboreDepth.expression = head
            elif kind == 'countersink':
                f.countersinkDiameter.expression, f.countersinkAngle.expression = head
            if depth:
                adsk.fusion.DistanceExtentDefinition.cast(f.extentDefinition).distance.expression = depth

        return self.step(key, name, make, update, spec=(kind, diameter, depth, head, points, spec), uses=uses,
                         read=lambda f: f.holeDiameter.expression, fixed=(('kind', kind), ('through all', not depth)))

    # ---- Features on bodies ----

    # items() (bodies or features) mirrored across plane. combine joins each copy to its original.
    # compute: see rect_pattern.
    def mirror(self, key, name, items, plane, combine=False, body_name=None, compute=None, spec=(), uses=()):
        mf = self.comp.features.mirrorFeatures
        how, how_said, how_fixed = _compute(compute, False)

        def make():
            mi = mf.createInput(_collection(items()), _get(plane))
            if combine:
                mi.isCombine = True
            if how is not None:
                mi.patternComputeOption = how
            f = mf.add(mi)
            if body_name:
                self._name_body(f, body_name)
            return f

        def update(f):  # slow-ok: step() logs it as "edit"
            want = items()
            have = f.inputEntities
            if not _same_entities(want, [have.item(i) for i in range(have.count)]):
                f.inputEntities = _collection(want)
            f.mirrorPlane = _get(plane)
            if body_name:
                self._name_body(f, body_name)

        return self.step(key, name, make, update, spec=(_axis_name(_get(plane)), combine, items, body_name, spec) + how_said, uses=uses,
                         fixed=(('combine', bool(combine)),) + (how_fixed if compute else ()))

    # items() (bodies or features) turned about axis: n copies counting the original, the last one angle
    # away, or spread both ways with symmetric. compute and adjust: see rect_pattern.
    def circular_pattern(self, key, name, items, axis, n, angle='360 deg', symmetric=False, adjust=False, compute=None, spec=(), uses=()):
        cp = self.comp.features.circularPatternFeatures
        how, how_said, how_fixed = _compute(compute, adjust)

        def make():
            ci = cp.createInput(_collection(items()), _get(axis))
            ci.quantity = vi(n)
            ci.totalAngle = vi(angle)
            ci.isSymmetric = symmetric
            if how is not None:
                ci.patternComputeOption = how
            return cp.add(ci)

        def update(f):  # slow-ok: step() logs it as "edit"
            want = items()
            have = f.inputEntities
            if not _same_entities(want, [have.item(i) for i in range(have.count)]):
                f.inputEntities = _collection(want)
            f.quantity.expression, f.totalAngle.expression = n, angle
            if f.isSymmetric != symmetric:
                f.isSymmetric = symmetric

        said = (n, angle, symmetric, items, _axis_name(_get(axis)), spec) + how_said
        return self.step(key, name, make, update, spec=said, uses=uses,
                         read=lambda f: '%s;%s' % (f.quantity.expression, f.totalAngle.expression),
                         fixed=(('axis', _axis_name(_get(axis))),) + how_fixed)

    # items() copied along path() (a curve or a list, chain: see _route): n copies, spacing apart.
    # compute: see rect_pattern.
    def path_pattern(self, key, name, items, path, n, spacing, chain=True, compute=None, spec=(), uses=()):
        pp = self.comp.features.pathPatternFeatures
        feats = self.comp.features
        route = lambda: _route(feats, path(), chain)
        how, how_said, how_fixed = _compute(compute, False)

        def make():  # slow-ok: the step's "make" line covers it
            pi = pp.createInput(_collection(items()), route(), vi(n), vi(spacing), adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
            if how is not None:
                pi.patternComputeOption = how
            return pp.add(pi)

        def update(f):  # slow-ok: step() logs it as "edit"
            f.quantity.expression, f.distance.expression = n, spacing

        return self.step(key, name, make, update, spec=(n, spacing, items, path, chain, spec) + how_said, uses=uses,
                         read=lambda f: '%s;%s' % (f.quantity.expression, f.distance.expression),
                         fixed=(('items', items), ('path', path), ('chain', chain)) + (how_fixed if compute else ()))

    # body() cut in two by tool (a plane, face or body). extend: the tool goes on past its edges.
    # The split-body limit in the README applies: a Combine whose tools are the pieces can break.
    def split_body(self, key, name, body, tool, extend=True, spec=(), uses=()):
        sf = self.comp.features.splitBodyFeatures

        def make():  # slow-ok: the step's "make" line covers it
            return sf.add(sf.createInput(body(), _get(tool), extend))

        def update(f):  # slow-ok: step() logs it as "edit"
            f.setSplittingTool(_get(tool), extend)

        return self.step(key, name, make, update, spec=(_axis_name(_get(tool)), extend, body, spec), uses=uses,
                         fixed=(('body', body),))

    # Hollows a body: faces() are left open (a body instead of faces closes it all round), thickness inward.
    def shell(self, key, name, faces, thickness, spec=(), uses=()):
        sf = self.comp.features.shellFeatures

        def make():
            si = sf.createInput(_collection(faces()), False)
            si.insideThickness = vi(thickness)
            return sf.add(si)

        def update(f):  # slow-ok: step() logs it as "edit"
            want = faces()
            have = f.inputEntities
            if not _same_entities(want, [have.item(i) for i in range(have.count)]):
                # inputEntities can't be set, so the faces went unchanged and the shell was replaced (F49).
                if not f.setInputEntities(_collection(want), False):
                    raise Exception('Fusion refused the new faces')
            f.insideThickness.expression = thickness

        return self.step(key, name, make, update, spec=(thickness, faces, spec), uses=uses,
                         read=lambda f: f.insideThickness.expression)

    # bodies() scaled by factor about point (a sketch point, vertex or construction point), the same every way.
    def scale(self, key, name, bodies, point, factor, spec=(), uses=()):
        sf = self.comp.features.scaleFeatures

        def make():  # slow-ok: the step's "make" line covers it
            return sf.add(sf.createInput(_collection(bodies()), _get(point), vi(factor)))

        def update(f):  # slow-ok: step() logs it as "edit"
            f.scaleFactor.expression = factor

        return self.step(key, name, make, update, spec=(factor, bodies, _axis_name(_get(point)), spec), uses=uses,
                         read=lambda f: f.scaleFactor.expression, fixed=(('bodies', bodies), ('point', _axis_name(_get(point)))))

    # Takes body() out of the design from here on: a helper body that only shaped others.
    def remove(self, key, name, body, spec=(), uses=()):
        def make():  # slow-ok: the step's "make" line covers it
            return self.comp.features.removeFeatures.add(body())

        return self.step(key, name, make, spec=(body, spec), uses=uses)

    # ---- Joints. Hand-made joints carry no key, so a run leaves them alone. ----

    # A part of a component below this one, as seen from here, through the one place that component sits.
    def _seen_here(self, x):
        if getattr(x, 'assemblyContext', None) is not None:
            return x
        owner = _owner(x)
        if owner is None or owner.id == self.comp.id:
            return x
        occs = self.comp.allOccurrencesByComponent(owner)
        if occs.count != 1:
            raise Exception('%s sits in %d places under %s, so pass it as seen from the one you mean (createForAssemblyContext)' % (owner.name, occs.count, self.comp.name))
        return x.createForAssemblyContext(occs.item(0))

    # One side of a joint: a JointGeometry as given, or a joint origin or point (sketch point, vertex,
    # construction point), seen from this component.
    def _joint_side(self, x):
        x = _get(x)
        if x.objectType == adsk.fusion.JointGeometry.classType():
            return x
        x = self._seen_here(x)
        if x.objectType == adsk.fusion.JointOrigin.classType():
            return x
        return adsk.fusion.JointGeometry.createByPoint(x)

    # A joint past the timeline marker has no attributes to read, so it looked hand-made, and marking it
    # failed (an edit to one joint left the next one rolled back). The marker goes after it
    # first. Fusion edits a joint only with the marker before it, so update() moves it back after.
    def _bring_up(self, key, name):
        ent = self.known.get(key)
        if ent is not None and ent.isValid and ent.timelineObject.index >= self.tl.markerPosition:
            with self._slow('marker after %s' % name):
                ent.timelineObject.rollTo(False)

    # A joint that puts one where two is. one and two are functions that give a side (see _joint_side).
    # motion is rigid, revolute or slider, about or along axis (x, y or z of two). Offset, angle and flip
    # are set like in Fusion's joint dialog. Every value, the sides and the motion edit in place.
    def joint(self, key, name, one, two, motion='rigid', axis='z', offset=None, angle=None, flip=False, spec=(), uses=()):
        _check_motion(name, motion, axis)
        joints = self.comp.joints

        def make():  # slow-ok: the step's "make" line covers it
            ji = joints.createInput(self._joint_side(one), self._joint_side(two))
            _set_motion(ji, motion, axis)
            if offset is not None:
                ji.offset = vi(offset)
            if angle is not None:
                ji.angle = vi(angle)
            ji.isFlipped = flip
            return joints.add(ji)

        # New sides can remake the offset and angle, so those are read after, as with fillets.
        def update(j):  # slow-ok: step() logs it as "edit"
            j.geometryOrOriginOne = self._joint_side(one)
            j.geometryOrOriginTwo = self._joint_side(two)
            _set_motion(j, motion, axis)
            j.offset.expression = offset or '0 cm'
            j.angle.expression = angle or '0 deg'
            j.isFlipped = flip
            j.timelineObject.rollTo(False)  # Edited with the marker before it, marked with the marker after.

        def read(j):
            return '%s;%s;%s;%s' % (_motion_of(j), j.offset.expression, j.angle.expression, j.isFlipped)

        self._bring_up(key, name)
        return self.step(key, name, make, update, spec=(one, two, motion, axis, offset, angle, flip, spec), uses=uses, read=read)

    # A joint that keeps two parts where they are now. one and two give the occurrences. A rigid one needs
    # nothing more. A revolute or slider one turns or slides at at (see _joint_side), about or along axis.
    def as_built_joint(self, key, name, one, two, motion='rigid', axis='z', at=None, spec=(), uses=()):
        _check_motion(name, motion, axis)
        if motion != 'rigid' and at is None:
            raise Exception('%s: a %s as-built joint needs at=, the point it moves about' % (name, motion))
        joints = self.comp.asBuiltJoints

        def make():  # slow-ok: the step's "make" line covers it
            ai = joints.createInput(_get(one), _get(two), self._joint_side(at) if at is not None else None)
            _set_motion(ai, motion, axis)
            return joints.add(ai)

        # Fusion can't change which two parts it holds, so new parts replace it.
        def update(j):  # slow-ok: step() logs it as "edit"
            if not _same_entities([j.occurrenceOne, j.occurrenceTwo], [_get(one), _get(two)]):
                raise Exception('it joins other parts now')
            _set_motion(j, motion, axis, *([self._joint_side(at)] if at is not None else []))
            j.timelineObject.rollTo(False)

        self._bring_up(key, name)
        return self.step(key, name, make, update, spec=(one, two, motion, axis, at, spec), uses=uses, read=_motion_of)

    def _remove_dropped(self):
        for it in reversed(timeline_items(self.tl)):
            key = _attr(it.entity, 'key')
            if key and key not in self.visited:
                self.touched.append(('removed', it.entity.name, 'the script no longer has it'))
                with self._slow('delete %s, the script no longer has it' % it.entity.name):
                    it.entity.deleteMe()
                del self.known[key]
                self.counts['removed'] += 1
                self.structure_changed = True

    def _remove_dropped_params(self):
        # Parameters this library made that the script no longer lists. One that something
        # still uses stays, and goes on a later run. Used ones can free up others, so go round.
        # A script that drops all its parameters drops them all (B9); before, it dropped none.
        attrs = self.des.attributes
        left = [a.name[len('wrote.'):] for a in attrs.itemsByGroup(GROUP) if a.name.startswith('wrote.')]
        left = [n for n in left if n not in self.params_seen]
        for i in range(len(left)):
            for n in list(left):
                p = self.des.userParameters.itemByName(n)
                if p is None or p.dependentParameters.count == 0:
                    if p:
                        p.deleteMe()  # slow-ok: nothing uses it
                    for prefix in ('wrote.', 'saw.', 'range.'):
                        a = attrs.itemByName(GROUP, prefix + n)
                        if a:
                            a.deleteMe()  # slow-ok: an attribute
                    left.remove(n)
                    self.structure_changed = True
                    self.log.append('parameter removed: %s, the script no longer has it' % n)
        for n in left:
            self.log.append('parameter %s is no longer in the script, but something still uses it' % n)

    # The script's parameters that no feature or sketch dimension uses, directly or through other
    # parameters, as (name, is a favorite). One only Python reads is among them (fusion/rules.md rule 9).
    def _unused_params(self):
        ups = self.des.userParameters
        used = {}

        def uses(p):
            if p.name not in used:
                used[p.name] = False  # Fusion allows no loops, but a stop costs nothing.
                used[p.name] = any(adsk.fusion.ModelParameter.cast(d) is not None or (ups.itemByName(d.name) is not None and uses(d))
                                   for d in p.dependentParameters)
            return used[p.name]
        out = []
        for n in self.params_seen:
            p = ups.itemByName(n)
            if p is not None and not uses(p):
                out.append((n, p.isFavorite))
        return out

    def _remove_retired(self):
        # Last first, since a later sketch can project from an earlier one.
        for old in reversed(self.retired):
            if old.isValid:
                with self._slow('delete %s' % old.name):
                    old.deleteMe()
        self.retired = []

    def _drop_group(self, group):
        for collapsed in (group.isCollapsed, not group.isCollapsed):
            group.isCollapsed = collapsed
            try:
                group.deleteMe(False)  # slow-ok: inside finish()'s "regroup" line
                return True
            except Exception as err:
                why = str(err).split(' - ')[-1].strip()
        self.log.append('could not regroup %s: %s' % (group.name, why))
        group.isCollapsed = False
        return False

    # The groups this library made, so a group the script renamed or dropped can follow it, and hand-made
    # groups are left alone (H5, H6, I2). Written only when it changes.
    def _made_groups(self, names=None):
        a = self.des.attributes.itemByName(GROUP, 'groups')
        old = json.loads(a.value) if a else []
        if names is not None and sorted(names) != sorted(old):
            self.des.attributes.add(GROUP, 'groups', json.dumps(sorted(names)))
        return set(old)

    # A group the script renamed (or the component it's named after) keeps its steps under the new
    # name. One the script dropped is taken apart, its steps stay. Done first, so a new group never
    # goes around an old one.
    def _follow_groups(self, have, members, pos):
        stale = [n for n in have if n in self.made_groups and n not in self.group_order]
        for n in self.group_order:
            ix = [pos[k] for k in self.group_keys.get(n, []) if k in pos]
            if n in have or len(ix) < 2:
                continue
            old = [g for g in stale if members.get(g) == set(range(min(ix), max(ix) + 1))]
            if old:
                have[n] = have.pop(old[0])
                have[n].name = n
                members[n] = members.pop(old[0])
                stale.remove(old[0])
                self.log.append('group %s renamed to %s, as the script has it' % (old[0], n))
        for n in stale:
            if self._drop_group(have.pop(n)):
                members.pop(n, None)
                self.log.append('group %s taken apart, the script no longer has it. Its steps stay.' % n)

    def _regroup(self):
        have = {g.name: g for g in self.tl.timelineGroups}
        self.made_groups = self._made_groups()
        stale = [n for n in have if n in self.made_groups and n not in self.group_order]
        if not self.structure_changed and not stale and all(n in have for n in self.group_order):
            return
        members = {}
        for it in timeline_items(self.tl):
            if it.parentGroup:
                members.setdefault(it.parentGroup.name, set()).add(it.index)
        # Read before any group is made: a step inside a new group has no number.
        pos = {k: self.known[k].timelineObject.index for keys in self.group_keys.values() for k in keys
               if k in self.known and self.known[k].isValid}
        self._follow_groups(have, members, pos)
        # Last group first, so adding one doesn't shift the numbers of the others.
        for n in reversed(self.group_order):
            # A step deleted along with one it depended on has no timeline item any more.
            ix = [pos[k] for k in self.group_keys.get(n, []) if k in pos]
            if len(ix) < 2:
                continue  # Fusion won't make a group of one item.
            first, last = min(ix), max(ix)
            if members.get(n) == set(range(first, last + 1)):
                continue
            # A component's own steps with one of its groups between them: no group for the component.
            # Fusion refused it when the inner group was new and wrapped it when the group was old, so a
            # rerun added a group the first run didn't have (E7).
            inner = {pos[k] for g, keys in self.group_keys.items() if g != n for k in keys if k in pos}
            if inner & set(range(first, last + 1)):
                self.log.append('no group for %s: its own steps sit around its other groups, and Fusion has no group inside a group' % n)  # H3
                continue
            if n in have and not self._drop_group(have[n]):
                continue
            try:
                self.tl.timelineGroups.add(first, last).name = n
            except Exception as err:
                self.log.append('could not group %s: %s' % (n, str(err).split(' - ')[-1].strip()))
        self._made_groups([g.name for g in self.tl.timelineGroups if g.name in self.group_order])

    def problems(self):
        return ['%s: %s' % (it.name, it.errorOrWarningMessage) for it in timeline_items(self.tl) if it.healthState == ErrorState]

    # A warning still builds, but the feature has lost something (an edge, a profile), so a
    # parameter that causes one is not robust. A sketch that can't solve a new value keeps its old shape
    # and warns only on itself: its timeline step stays healthy, so sketches are asked too.
    def warnings(self):
        out = ['%s: %s' % (it.name, it.errorOrWarningMessage) for it in timeline_items(self.tl) if it.healthState == WarningState]
        return out + ['%s: the sketch did not solve, so it kept its old shape' % s.name for c in self.des.allComponents
                      for s in c.sketches if _attr(s, 'key') and s.healthState != Healthy]

    def foreign(self):
        return [it.name for it in timeline_items(self.tl) if not _attr(it.entity, 'key')]

    def unresolved(self):
        return [s.name for c in self.des.allComponents for s in c.sketches if _attr(s, 'key') and not s.isFullyConstrained]

    # The first profile, for a step given no profile=. Which profile is first can change when a value
    # changes, so a sketch with more than one says so, once per step (fusion/rules.md rule 13).
    def _first_profile(self, s, name):
        if s.profiles.count > 1 and name not in self.profile_warned:
            self.profile_warned.append(name)
            self.log.append('%s: the sketch has %d profiles and no profile= was given, so the first is used; pass profile= '
                            'that picks by a point inside or by area' % (name, s.profiles.count))
        return s.profiles.item(0)

    # Each body as (part, name, volume in mm3, box corners in mm), sorted: what must come back after a
    # trial body by body, so a body that moved or swapped size with another can't hide in the totals.
    def bodies(self):
        out = []
        for c in self.des.allComponents:
            part = '(root)' if c == self.root else c.name
            for x in c.bRepBodies:
                bb = x.boundingBox
                box = (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z, bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)
                out.append((part, x.name, round(x.volume * 1000, 3), tuple(round(v * 10, 4) for v in box)))
        return sorted(out)

    # Every body's volume in mm3, the body count and the face count: what must come back after a trial.
    def size(self):
        bodies = [x for c in self.des.allComponents for x in c.bRepBodies]
        return (round(sum(x.volume for x in bodies) * 1000, 1), len(bodies), sum(x.faces.count for x in bodies))

    # The parameter test (README § Testing your design, fusion/rules.md rule 19). Each trial sets
    # parameters and lets Fusion recompute. A new error or warning, a sketch that is no longer fully
    # constrained, a value Fusion refuses, or a problem from more(des) fails the trial. Then the old
    # values go back, and the design must come back the same: no new error, and size(des) as before.
    # It runs in stages, quick ones first, and stops after the first stage with a failure, so a quick
    # failure shows up fast:
    #   ends: each parameter alone at the low and the high end of its range. When an end fails, the
    #     gap to the value that works is halved until the edge is found (self.trials_held).
    #   steps: each parameter alone one step either side of its value.
    #   extremes: every parameter with a range at its low end at once, then all at the high end.
    #   random: runs sets of random values from every range, seed logged, so a failed set can be
    #     tried again. Runs only when asked for.
    # A parameter with no range is tried a step either side (trial_values) in ends and steps, and left
    # out of extremes and random.
    #   values: (name, value) pairs; a name here is tried at these values in ends and steps instead.
    #   skip: names not to try, each with its reason in a comment in the script.
    #   only: names to try, the rest are skipped (the mode check:a,b, split_mode).
    #   stop: a file that ends the trials when it shows up, since Fusion can't stop a running script.
    # Run it after a save, so a broken design can go back. Stops at the first trial the design doesn't
    # come back from: a lost reference stays lost, so every later trial would only repeat it. Returns
    # False then, and the caller aborts. Failed trials are in self.trials_failed and the log.
    def trials(self, values=(), skip=(), only=None, stop=None, size=None, more=None, tests=TESTS, runs=20, seed=None):
        size = size or (lambda des: self.size())
        ps = self.des.userParameters
        attrs = self.des.attributes
        given = {}
        for name, value in values:
            given.setdefault(name, []).append(value)
        unknown = [n for n in list(given) + list(skip) + list(only or []) if not ps.itemByName(n)]
        if unknown:
            raise Exception('the parameter test names %s, but the design has no such parameter' % ', '.join(sorted(set(unknown))))
        odd = [t for t in tests if t not in TESTS + ('random',)]
        if odd:
            raise Exception('the parameter test has no test %s; it has %s and random' % (', '.join(odd), ', '.join(TESTS)))
        # Each parameter in the test: (name, unit, grid of its range's values or None, index of its value).
        params, no_range, formulas = [], [], []
        for i in range(ps.count):
            p = ps.item(i)
            if p.name in skip or (only is not None and p.name not in only):
                continue
            r = self.ranges.get(p.name)
            if r is None:
                a = attrs.itemByName(GROUP, 'range.' + p.name)
                r = ranges.load(a.value) if a else None
            v = ranges.number(p.expression, p.unit)
            if r and v is not None:
                g = ranges.grid(*r)
                at = min(range(len(g)), key=lambda k: abs(g[k] - v))
                if abs(g[at] - v) > 1e-6:
                    self.log.append('%s = %s is not one of its range\'s values; the test starts from %s' % (p.name, p.expression, ranges.text(g[at], p.unit)))
                params.append((p.name, p.unit, g, at))
            elif p.name in given or trial_values(p.expression):
                if p.name not in given:
                    no_range.append(p.name)
                params.append((p.name, p.unit, None, None))
            else:
                formulas.append(p.name)
        # Said, so the test doesn't look like it covered every parameter.
        if formulas:
            self.log.append('not tried, a formula: %s' % ', '.join(formulas))
        if no_range:
            self.log.append('no range for %s: tried a step either side, and left out of extremes and random. Give each one range= '
                            'and step= (fusion/lib/README.md, The parameter test)' % ', '.join(no_range))
        ranged = [x for x in params if x[2]]
        base = set(self.problems() + self.warnings() + self.unresolved())
        start = size(self.des)
        start_bodies = self.bodies()
        self.trials_failed = []
        self.trials_held = {}  # name -> (lowest, highest) value that works, from the ends stage
        self.log.append('parameter test: %s, %d parameters, size %s' % (', '.join(tests), len(params), start))
        done = [0]
        seen = set()

        class Stop(Exception):
            pass

        class Lost(Exception):
            pass

        def one(changes, label=None, first=()):
            # Sets the (name, value) changes, checks, puts them back. Returns the problems, [] for
            # none. A one-parameter trial already made in an earlier stage isn't made again. first:
            # changes set and computed before these, for a trial that starts somewhere else.
            if len(changes) == 1 and label is None:
                if changes[0] in seen:
                    return None
                seen.add(changes[0])
            if stop and os.path.exists(stop):
                os.remove(stop)
                raise Stop()
            done[0] += 1
            label = label or '%s = %s' % changes[0]
            names = list(dict.fromkeys(n for n, v in list(first) + list(changes)))
            olds = [(n, ps.itemByName(n).expression) for n in names]
            try:
                with self._slow('trial %d: %s' % (done[0], label)):
                    for n, v in first:
                        ps.itemByName(n).expression = v
                    adsk.doEvents()
                    for n, v in changes:
                        ps.itemByName(n).expression = v
                    adsk.doEvents()
                bad = [x for x in self.problems() + self.warnings() if x not in base]
                bad += ['%s is not fully constrained' % x for x in self.unresolved() if x not in base]
                bad += list(more(self.des)) if more else []
            except Exception as err:
                bad = ['refused: %s' % str(err).split(' - ')[-1].strip()]
            with self._slow('put %s back' % ', '.join('%s = %s' % x for x in olds)):
                for n, old in reversed(olds):
                    ps.itemByName(n).expression = old
                adsk.doEvents()
            what = label if len(changes) == 1 else '%s (%s)' % (label, ', '.join('%s = %s' % x for x in changes))
            self.log.append('trial %s: %s' % (label, 'FAILED: ' + '; '.join(bad) if bad else 'ok'))
            if bad:
                if len(changes) > 1:
                    self.log.append('  the set: %s' % ', '.join('%s = %s' % x for x in changes))
                self.trials_failed.append('%s: %s' % (what, '; '.join(bad)))
            now, broke = size(self.des), [x for x in self.problems() if x not in base]
            moved = _body_changes(start_bodies, self.bodies())
            if broke or moved or not _same_size(now, start):
                self.log.append('DID NOT COME BACK after %s: size %s, was %s%s%s' % (what, now, start, ', errors: %s' % broke if broke else '',
                                                                                  ', bodies: %s' % '; '.join(moved[:10]) if moved else ''))
                raise Lost()
            return bad

        def ends(name, unit, g, at):
            last = len(g) - 1
            held = [at, at]
            for side, end in ((0, 0), (1, last)):
                if end == at:
                    continue
                if not one([(name, ranges.text(g[end], unit))]):
                    held[side] = end
                    continue
                # The end failed: halve the gap to the last value that worked to find the edge.
                good, bad_i = at, end
                while abs(bad_i - good) > 1:
                    mid = (good + bad_i) // 2
                    good, bad_i = (good, mid) if one([(name, ranges.text(g[mid], unit))]) else (mid, bad_i)
                held[side] = good
            self.trials_held[name] = (ranges.text(g[held[0]], unit), ranges.text(g[held[1]], unit))
            if held != [0, last]:
                self.log.append('RANGE TOO WIDE: %s works from %s to %s, its range is %s to %s'
                                % ((name,) + self.trials_held[name] + (ranges.text(g[0], unit), ranges.text(g[last], unit))))

        try:
            for t, test in enumerate(tests):
                failed = len(self.trials_failed)
                self.log.append('--- %s' % test)
                if test in ('ends', 'steps'):
                    for name, unit, g, at in params:
                        if name in given:
                            for value in given[name]:
                                one([(name, value)])
                        elif g is None:
                            for value in trial_values(ps.itemByName(name).expression):
                                one([(name, value)])
                        elif test == 'ends':
                            ends(name, unit, g, at)
                        else:
                            for k in (at - 1, at + 1):
                                if 0 <= k < len(g):
                                    one([(name, ranges.text(g[k], unit))])
                elif not ranged:
                    self.log.append('no parameter has a range, so there is no %s stage' % test)
                elif test == 'extremes':
                    low = [(n, ranges.text(g[0], u)) for n, u, g, at in ranged]
                    high = [(n, ranges.text(g[-1], u)) for n, u, g, at in ranged]
                    one(low, 'all low')
                    one(high, 'all high')
                    # Fusion recomputes after each value, so the way between two sets matters: a sketch
                    # that solves from the usual values can fail from the far end of every range.
                    one(high, 'all low, then all high', first=low)
                else:
                    seed = seed if seed is not None else int(time.time())
                    rng = random.Random(seed)
                    self.log.append('random sets: %d, seed %d' % (runs, seed))
                    for k in range(runs):
                        one([(n, ranges.text(rng.choice(g), u)) for n, u, g, at in ranged], 'random %d of %d' % (k + 1, runs))
                if len(self.trials_failed) > failed and t + 1 < len(tests):
                    self.log.append('the %s stage failed, so %s did not run' % (test, ', '.join(tests[t + 1:])))
                    break
        except Stop:
            self.log.append('parameter test stopped by the stop file after %d trials' % done[0])
            return True
        except Lost:
            return False
        self.log.append('parameter test: %d of %d trials failed' % (len(self.trials_failed), done[0]))
        return True

    # A save reaches the cloud a little later, and until then the file still reads as the old
    # version. Opening the tab's own file after a restore point would miss the restore point.
    def _last_saved(self, df):
        data = adsk.core.Application.get().data
        if self.go_back_to is not None:
            return self._version(data, df, self.go_back_to)
        with self._slow('wait for the last save to reach the cloud'):
            for i in range(120):
                latest = data.findFileById(df.id).latestVersion
                if self.restore_from is None or latest.versionNumber > self.restore_from:
                    return latest
                adsk.doEvents()
                time.sleep(0.5)
        self.log.append('the restore point has not shown up yet, it will be version %d' % (self.restore_from + 1))
        return latest

    # A version from the file's history, once the cloud has it.
    def _version(self, data, df, n):
        with self._slow('wait for version %d in the cloud' % n):
            for i in range(120):
                f = data.findFileById(df.id)
                if f.latestVersionNumber >= n:
                    break
                adsk.doEvents()
                time.sleep(0.5)
        if f.latestVersion.versionNumber == n:
            return f.latestVersion
        for v in f.versions:
            if v.versionNumber == n:
                return v
        raise Exception('version %d is not in the file\'s history' % n)

    # Never raises: the run's own error is the one to report. A tab that can't be closed stays
    # half-built, so it is marked with the last good version, and the next run there goes back to it
    # (Decision 1). Closing without saving drops the mark with everything else.
    def _go_back(self):
        if not (self.doc and self.doc.dataFile):
            self.log.append('NOT GOING BACK: the design was never saved, so there is no version to go back to. The tab is as the run left it.')
            return
        try:
            df = self._last_saved(self.doc.dataFile)
        except Exception as err:
            self.log.append('COULD NOT GO BACK: the last good version was not found: %s. The tab is as the run left it.' % err)
            return
        n = df.versionNumber
        try:
            self.des.attributes.add(GROUP, 'go_back_to', str(n))
        except Exception as err:
            self.log.append('could not mark the tab with version %d: %s' % (n, err))
        try:
            with self._slow('close the tab without saving'):
                _close(self.doc)
        except Exception as err:
            if self.doc.isValid:
                self.log.append('COULD NOT GO BACK: %s. This tab is half-built; version %d is the last good one. The next run here goes back to it if it fails, and saves no restore point of this tab.' % (err, n))
                return
        try:
            with self._slow('open version %d' % n):
                adsk.core.Application.get().documents.open(df)
        except Exception as err:
            self.log.append('COULD NOT GO BACK: the tab is closed, and version %d could not be opened: %s. Nothing was saved; the saved design is fine.' % (n, err))
            return
        self.log.append('went back to the last saved version, %d, nothing else was saved' % n)

    # Each group as it was left, found by name, so a group the run made again comes back collapsed if
    # the old one was (H7). A new group stays the way Fusion makes it, collapsed.
    def _restore_groups(self):
        for g in self.tl.timelineGroups:
            want = self.group_states.get(g.name)
            if want is not None and g.isCollapsed != want:
                g.isCollapsed = want

    # After the parameter test. Every trial put its values back, but Fusion still counts the tab as
    # changed: closing it asks the person to save, and the runner refuses its next run. So this closes
    # the tab without saving and opens the saved version again. Call it last: des and doc are stale
    # afterwards. Never raises, like _go_back.
    def back_to_saved(self):
        self.log.append('parameter test done: closing its unsaved changes')
        self._go_back()

    # Something raised partway through.
    def abort(self, why):
        self.log.append('STOPPED: %s' % why)
        try:
            with self._slow('marker to the end'):
                self.tl.moveToEnd()
            self._restore_groups()
        except Exception as err:
            self.log.append('could not put the marker and groups back before going back: %s' % err)
        self._go_back()

    # Puts the marker back at the end and checks every feature, hand-made ones included.
    def finish(self):
        with self._slow('marker to the end'):
            self.tl.moveToEnd()
        self._remove_retired()
        self._remove_dropped()
        # Deleting a dropped or retired step takes the steps built on it, and some of those the script
        # still has. They are made again at their spots. Before, the run went back and said "run again",
        # and every run did the same, since nothing was saved.
        lost = [k for k in self.visited if not self.known[k].isValid]
        if lost:
            self._rebuild(lost, 'a step the script dropped', 'deleted with a step the script dropped or replaced')
            with self._slow('marker to the end'):
                self.tl.moveToEnd()
        self._remove_dropped_params()
        for f, body_name in self.names_later:
            if f.isValid and f.bodies.count and f.bodies.item(0).name != body_name:
                f.bodies.item(0).name = body_name
        with self._slow('regroup'):
            self._regroup()
        with self._slow('marker to the end'):
            self.tl.moveToEnd()
        self._restore_groups()
        c = self.counts
        self.log.append('steps: %d same, %d created, %d updated, %d replaced, %d removed' % (c['same'], c['created'], c['updated'], c['replaced'], c['removed']))
        for what, name, why in self.touched:
            self.log.append('  %s %s: %s' % (what, name, why))
        for item in self.params_set:
            self.log.append('parameter set: ' + item)
        for item in self.params_kept:
            self.log.append('parameter kept, it was changed by hand: ' + item)
        for item in self.names_kept:
            self.log.append('name kept, it was changed by hand: ' + item)
        for item in self.hand_kept:
            self.log.append('changed by hand, kept: ' + item)
        foreign = self.foreign()
        if foreign:
            self.log.append('left alone, not made by this script: %s' % ', '.join(foreign))
        warned = self.warnings()
        if warned:
            self.log.append('WARNINGS: %s' % '; '.join(warned))
        for p, favorite in self._unused_params():
            self.log.append('parameter %s: nothing in the design uses it, so changing it does nothing and the parameter test proves nothing%s'
                            % (p, '. It is a favorite, so its Customize slider does nothing' if favorite else ''))
        # A bare number in an expression is read in the design's units, so '6' is 6 inches in an inch design.
        if self.des.unitsManager.distanceDisplayUnits != adsk.fusion.DistanceUnits.MillimeterDistanceUnits:
            self.log.append('the design\'s units are not mm, so a bare number in an expression is read in its units: '
                            'set mm before the first parameter, as the template does')
        bad = [x for x in self.problems() if x.split(': ')[0] not in self.errors_at_start]
        old = [n for n in self.errors_at_start if any(x.split(': ')[0] == n for x in self.problems())]
        if old:
            self.log.append('already broken before this run, left as it was: %s' % ', '.join(old))
        bad += ['%s: gone' % n for n in self.foreign_at_start if n not in foreign]
        # Fusion keeps a step whose reference was deleted, on cached geometry, with only a warning.
        bad += ['%s: made by hand, and it warns since this run' % it.name for it in timeline_items(self.tl)
                if not _attr(it.entity, 'key') and it.healthState == WarningState and it.name not in self.foreign_warned_at_start]
        # A step deleted with one the script dropped is made again above; this is if that went wrong too.
        bad += ['%s: deleted with a step it used, and not made again' % k for k in self.visited if not self.known[k].isValid]
        if bad:
            self.log.append('BROKEN: %s' % '; '.join(bad))
            self._go_back()
            return False
        mark = self.des.attributes.itemByName(GROUP, 'go_back_to')
        if mark:
            mark.deleteMe()  # slow-ok: an attribute
            self.whole_again = True
            self.log.append('this tab is whole again, so the mark of the last good version is gone')
        return True

    # Saves a new version, only if this run changed something, or made a half-built tab whole again: the
    # last run that couldn't go back left changes in it that no version has (K8).
    def save(self, note):
        if self.doc and (self.structure_changed or self.params_set or self.whole_again):
            with self._slow('save'):
                said = self.doc.save(note)
            self.log.append('saved: %s' % said)
