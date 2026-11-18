# The scenarios of upsert-test-scenarios.md § 3, one function each. A scenario gets a Scenario (S) from
# upsert_harness, builds version 1 in a new tab, changes something, builds version 2, checks what is
# special to it, then runs the § 2 checks with S.standard().
import os, time
import adsk.core, adsk.fusion
import cad_apprentice
import upsert_harness as H
import upsert_model as M
from upsert_model import variant
from cad_apprentice import _attr, timeline_items, open_groups, close_groups, slow

SCENARIOS = {}
ORDER = []
# Writes a progress line. upsert_suite sets it; the hand edits below use it for a line around each slow
# call (fusion/rules.md).
note = None


def scenario(fn):
    sid = fn.__name__.upper() if fn.__name__[0] != '_' else fn.__name__[1:]
    SCENARIOS[sid] = fn
    ORDER.append(sid)
    return fn


def first(S, v=None, label='v1'):
    doc, des = S.tab()
    r = S.run(doc, des, v or variant(), label)
    S.need(r, 'version 1')
    return doc, des, r


def item(des, name):
    for it in timeline_items(des.timeline):
        if it.name == name:
            return it
    return None


def keyed(des, key):
    for it in timeline_items(des.timeline):
        if _attr(it.entity, 'key') == key:
            return it
    return None


def unchanged_by_refusal(S, r, tag):
    # A refused run must leave the design as it was: timeline, fingerprints, bodies and parameters (F47).
    if r['ok'] or not r.get('after'):
        return
    for line in H.compare(r['before'], r['after'], fp=True):
        S.fail('%s: the refused run changed the design: %s' % (tag, line))


def logged(r, text):
    return any(text in line for line in r['log'])


def moves(r):
    return [l for l in r['log'] if l.startswith('moved ') or l.startswith('could not move')]


def touched(r, what=None):
    return [t for t in r.get('touched', []) if what is None or t[0] == what]


# A. First build and plain reruns

@scenario
def a1(S):
    doc, des, r = first(S)
    S.expect(H.changed(r) == {'created': r['counts']['created']}, 'a fresh build only creates: %s' % r['counts'])
    S.expect(r['counts']['created'] == len(r['visited']), '%d created for %d steps' % (r['counts']['created'], len(r['visited'])))
    snap = S.standard(doc, des, variant(), r)
    return {'baseline': {'steps': len(r['visited']), 'items': len(snap['items']), 'bodies': snap['bodies'], 'seconds': r['seconds']}}


@scenario
def a2(S):
    doc, des, r = first(S)
    r2 = S.run(doc, des, variant(), 'v1 again')
    S.need(r2)
    S.expect(not H.changed(r2), 'a rerun with no change: %s' % H.changed(r2))
    S.standard(doc, des, variant(), r2, rerun=False)


@scenario
def a3(S):
    doc, des, r = first(S)
    tl = des.timeline
    # A fresh build leaves every new group collapsed, the way Fusion makes them. So all are opened
    # first, and two are shut by hand.
    open_groups(tl)
    shut = []
    for g in tl.timelineGroups:
        if g.name in ('Outer', 'Cap'):
            g.isCollapsed = True
            shut.append(g.name)
    S.expect(len(shut) == 2, 'groups to collapse: %s' % [g.name for g in tl.timelineGroups])
    r2 = S.run(doc, des, variant(), 'collapsed')
    S.need(r2)
    S.expect(not H.changed(r2), 'nothing changes: %s' % H.changed(r2))
    now = {g.name: g.isCollapsed for g in tl.timelineGroups}
    S.expect(all(now.get(n) for n in shut), 'groups collapsed again after the run: %s' % now)
    S.expect(not any(c for n, c in now.items() if n not in shut), 'only the groups shut by hand are collapsed: %s' % now)
    S.standard(doc, des, variant(), r2)


@scenario
def a4(S):
    doc, des, r = first(S)
    tl = des.timeline
    open_groups(tl)  # Steps in a collapsed group have no number, so the marker can't be put among them.
    tl.markerPosition = 5
    r2 = S.run(doc, des, variant(), 'rolled back')
    S.need(r2)
    S.expect(tl.markerPosition == tl.count, 'the marker is at the end: %d of %d' % (tl.markerPosition, tl.count))
    S.expect(not H.changed(r2), 'nothing changes: %s' % H.changed(r2))
    S.expect(not logged(r2, 'left alone'), 'nothing looks hand-made: %s' % [l for l in r2['log'] if 'left alone' in l])
    S.standard(doc, des, variant(), r2)


@scenario
def a5(S):
    # A key written twice in the script stops the run before its first step (precheck.py). A key chosen
    # at run time, like 'dup' here, can only be caught at its second use, after the steps before it ran.
    # So the run goes back to the last save, and nothing in the design changed.
    doc, des, fid, r = saved_first(S)
    n = H.latest_version(fid)
    before = H.snapshot(des)
    v2 = variant(spec={'base': ('v2',)})
    v2['order'] = M.ORDER + ['dup']
    r2 = S.run(doc, des, v2, 'key used twice', save_note='cad_apprentice test A5: v2')
    S.expect(not r2['ok'] and 'used twice' in (r2['error'] or ''), 'a clear error: %s' % r2['error'])
    went_back(S, r2, fid, n, before, 'A5')
    S.info['error'] = r2['error']


@scenario
def a7(S):
    # Measure only (F45): a tab that was never saved, with a hand edit, then a run that changes a value
    # and a run that fails. What the library did is recorded as a flag, so a change in it shows up.
    doc, des, r = first(S)
    hand_param(des, 'base_d', '35 mm')
    r2 = S.run(doc, des, set_param(variant(), 'base_w', '45 mm'), 'base_w')
    S.need(r2)
    kept = des.userParameters.itemByName('base_d').expression
    r3 = S.run(doc, des, set_param(variant(die_at='post'), 'base_w', '50 mm'), 'dies')
    back = [l for l in r3['log'] if 'GO BACK' in l or 'went back' in l or 'never saved' in l]
    S.info['after the failed run'] = {'tab open': doc.isValid, 'go-back lines': back}
    S.flag('unsaved tab: the change run kept the hand value: %s; the failed run said: %s; the tab is still open: %s' % (kept == '35 mm', back, doc.isValid))


# The bug scenarios, run first.

def reordered(order, block, after):
    # order with the keys in block taken out and put back right after the key `after`.
    rest = [k for k in order if k not in block]
    i = rest.index(after) + 1
    return rest[:i] + list(block) + rest[i:]


def order_of(des, keys):
    # Read with the groups open: a step in a collapsed group has no usable number.
    tl = des.timeline
    opened = open_groups(tl)
    ix = {}
    for i in range(tl.count):
        k = _attr(tl.item(i).entity, 'key')
        if k in keys:
            ix[k] = i
    close_groups(opened)
    return [k for k in sorted(ix, key=ix.get)]


@scenario
def e3(S):
    # A block of steps (round and chamfer) moved before the cuts.
    doc, des, r = first(S)
    v2 = variant(order=reordered(M.ORDER, ['hole_sketch', 'hole_cut', 'hole_pattern'], 'chamfer'))
    r2 = S.run(doc, des, v2, 'block moved')
    S.need(r2)
    S.expect(not touched(r2, 'replaced'), 'nothing replaced: %s' % touched(r2, 'replaced'))
    S.expect(bool(moves(r2)), 'the log lists the moves')
    S.expect(order_of(des, v2['order']) == v2['order'], 'timeline order is the script order: %s' % order_of(des, v2['order']))
    S.info['moves'] = moves(r2)
    S.info['touched'] = touched(r2)
    S.standard(doc, des, v2, r2)


@scenario
def e4(S):
    # One step moved: canReorder/reorder take an index.
    doc, des, r = first(S)
    v2 = variant(order=reordered(M.ORDER, ['hole_pattern'], 'post'))
    r2 = S.run(doc, des, v2, 'one step moved')
    S.need(r2)
    S.expect(any(l.startswith('moved Hole pattern') for l in r2['log']), 'moved, and the log says so: %s' % moves(r2))
    S.expect(not touched(r2, 'replaced'), 'nothing replaced: %s' % touched(r2, 'replaced'))
    S.info['moves'] = moves(r2)
    S.standard(doc, des, v2, r2)


@scenario
def g2(S):
    # A replace in the middle takes a step the script already passed. The chamfer picks
    # the first hole's top edge once the holes are cut, else the back bottom edge. Version 1 cuts the holes
    # first, so the chamfer is built on the hole cut. Version 2 moves the holes after the chamfer: the cut
    # can't move past the chamfer built on it, so it is replaced, and deleting it took the chamfer along.
    doc, des, r = first(S, variant(alt={'chamfer': 'holes'}))
    v2 = variant(alt={'chamfer': 'holes'}, order=reordered(M.ORDER, ['hole_sketch', 'hole_cut', 'hole_pattern'], 'chamfer'))
    r2 = S.run(doc, des, v2, 'round moved before the holes')
    S.info['run2'] = {k: r2.get(k) for k in ('ok', 'error', 'counts', 'touched')}
    S.info['log'] = [l for l in r2['log'] if not l.startswith('  step')]
    S.expect(r2['ok'] or 'could not' in (r2['error'] or '') or 'refus' in (r2['error'] or ''), 'it finishes, or refuses before deleting: %s' % r2.get('error'))
    S.expect(not logged(r2, 'deleted with a step it used'), 'no hole: %s' % [l for l in r2['log'] if 'deleted with' in l])
    unchanged_by_refusal(S, r2, 'G2')
    if r2['ok']:
        S.standard(doc, des, v2, r2)


@scenario
def g4(S):
    # A fillet with two edge sets, edited after its body changed (a sketch redraw under it).
    doc, des, r = first(S)
    v2 = variant(base_draw=M.base_outline_v2)
    r2 = S.run(doc, des, v2, 'base redrawn')
    S.need(r2)
    rounds = [t for t in touched(r2) if t[1] == 'Rounds']
    S.expect(rounds and rounds[0][0] == 'updated', 'the fillet is edited in place: %s' % rounds)
    S.expect(not logged(r2, 'could not edit Rounds'), 'no failed edit: %s' % [l for l in r2['log'] if 'could not edit' in l])
    S.info['touched'] = touched(r2)
    S.info['log'] = [l for l in r2['log'] if 'could not' in l]
    S.standard(doc, des, v2, r2)


@scenario
def h10(S):
    # A group's step deleted during the run: the post is dropped, and the round on its edges goes too.
    v1 = variant(order=M.ORDER[:6] + [('group', 'Post', ['post_sketch', 'post', 'round'])] + [k for k in M.ORDER[6:] if k not in ('post_sketch', 'post', 'round')])
    v1['uses']['round'] = ('base', 'post')  # Here the round comes before the rib join, so it can't use it.
    doc, des, r = first(S, v1)
    v2 = variant(order=M.ORDER[:6] + [('group', 'Post', ['round'])] + [k for k in M.ORDER[6:] if k not in ('post_sketch', 'post', 'round')])
    v2['alt']['round'] = 'one'
    v2['uses']['round'] = ('base',)  # The post is gone, and a uses naming no earlier step now stops the run.
    r2 = S.run(doc, des, v2, 'post dropped')
    S.info['run2'] = {k: r2.get(k) for k in ('ok', 'error', 'counts', 'touched')}
    S.info['log'] = [l for l in r2['log'] if not l.startswith('  step')]
    S.expect('NoneType' not in (r2.get('trace') or ''), 'no crash in regroup: %s' % (r2.get('trace') or '')[-400:])
    # Before, a BROKEN passed here, and every rerun was BROKEN the same way.
    S.need(r2)
    S.standard(doc, des, v2, r2)


@scenario
def c3(S):
    # A helper the draw function calls changes; the draw function itself doesn't.
    old = M.corner_tag
    try:
        doc, des, r = first(S)
        M.corner_tag = M.make_fn('def corner_tag(lines):\n    tag(lines.item(2).startSketchPoint, "corner")\n', 'corner_tag')
        r2 = S.run(doc, des, variant(), 'helper changed')
        S.need(r2)
        S.expect(any(t[1] == 'Base outline' for t in touched(r2)), 'the sketch reruns: %s' % touched(r2))
        S.info['touched'] = touched(r2)
        S.standard(doc, des, variant(), r2)
    finally:
        M.corner_tag = old


@scenario
def c4(S):
    # A value a function reads from outside changes: a global (RIB_SCALE), and a captured variable
    # (the radius, read by the fillet's sets lambda).
    old = M.RIB_SCALE
    try:
        doc, des, r = first(S)
        M.RIB_SCALE = '2'
        r2 = S.run(doc, des, variant(), 'global changed')
        S.need(r2)
        S.expect(any(t[1] == 'Rib outline' for t in touched(r2)), 'a changed global reruns the sketch: %s' % touched(r2))
        S.info['touched_global'] = touched(r2)
        v3 = variant(round_r=('round_r', 'round_r / 2'))
        r3 = S.run(doc, des, v3, 'captured value changed')
        S.need(r3)
        S.expect(any(t[1] == 'Rounds' for t in touched(r3)), 'a changed captured value reruns the fillet: %s' % touched(r3))
        S.info['touched_captured'] = touched(r3)
        S.standard(doc, des, v3, r3)
    finally:
        M.RIB_SCALE = old


@scenario
def c8(S):
    # A label changes in the script and nothing else: renamed in place, nothing rebuilt.
    doc, des, r = first(S)
    v2 = variant(names={'hole_cut': 'Hole cut, renamed', 'round': 'Rounded edges'})
    r2 = S.run(doc, des, v2, 'labels changed')
    S.need(r2)
    S.expect(item(des, 'Hole cut, renamed') is not None and item(des, 'Rounded edges') is not None, 'renamed: %s' % [i['name'] for i in H.snapshot(des)['items']])
    S.expect(not touched(r2, 'replaced') and not touched(r2, 'created'), 'nothing rebuilt: %s' % touched(r2))
    S.expect(logged(r2, 'renamed'), 'the log says so')
    S.info['log'] = [l for l in r2['log'] if not l.startswith('  step')]
    S.standard(doc, des, v2, r2)


@scenario
def j2(S):
    # A keyed feature is changed by hand (the base extrude's distance): that value stays, the run says so.
    doc, des, r = first(S)
    ext = adsk.fusion.ExtrudeFeature.cast(keyed(des, 'base').entity)
    opened = open_groups(des.timeline)  # A step in a collapsed group can't be rolled to.
    with slow(note, 'hand edit: base extrude distance'):
        ext.timelineObject.rollTo(True)
        d = adsk.fusion.DistanceExtentDefinition.cast(ext.extentOne)
        d.distance.expression = 'base_h + 2 mm'
        des.timeline.moveToEnd()
    close_groups(opened)
    r2 = S.run(doc, des, variant(), 'after the hand edit')
    S.need(r2)
    now = adsk.fusion.DistanceExtentDefinition.cast(adsk.fusion.ExtrudeFeature.cast(keyed(des, 'base').entity).extentOne).distance.expression
    S.expect(H.cad_apprentice._same(now, 'base_h + 2 mm'), 'the hand value stays: %s' % now)
    S.expect(any('by hand' in l and 'Base extrude' in l for l in r2['log']), 'the run reports it: %s' % [l for l in r2['log'] if not l.startswith('  ')])
    S.info['log'] = [l for l in r2['log'] if not l.startswith('  step')]

    def tweak(fdes):
        f = adsk.fusion.ExtrudeFeature.cast(keyed(fdes, 'base').entity)
        opened = open_groups(fdes.timeline)
        with slow(note, 'hand edit, on the fresh build: base extrude distance'):
            f.timelineObject.rollTo(True)
            adsk.fusion.DistanceExtentDefinition.cast(f.extentOne).distance.expression = 'base_h + 2 mm'
            fdes.timeline.moveToEnd()
        close_groups(opened)
    S.standard(doc, des, variant(), r2, fresh_tweak=tweak)


# Helpers for the scenarios below.

import os, re
import cad_apprentice
from cad_apprentice import vi, _same

SKETCHES = set(M.LABELS[k] for k in M.LABELS if k.endswith('_sketch'))


def set_param(v, name, expr=None, unit=None, comment=None, favorite=None):
    for p in v['params']:
        if p['name'] == name:
            for k, x in (('expr', expr), ('unit', unit), ('comment', comment), ('favorite', favorite)):
                if x is not None:
                    p[k] = x
            return v
    v['params'].append(dict(name=name, expr=expr, unit=unit or 'mm', comment=comment or '', favorite=bool(favorite)))
    return v


def drop_param(v, name):
    v['params'] = [p for p in v['params'] if p['name'] != name]
    return v


def rename_param(v, old, new, was=None):
    # The script renames parameter old to new: was= on it, and every expression in the model and the
    # other parameters names the new one.
    v['rename'][old] = new
    for p in v['params']:
        if p['name'] == old:
            p['name'], p['was'] = new, was or old
        p['expr'] = re.sub(r'\b%s\b' % re.escape(old), new, p['expr'])
    return v


def hand_param(des, name, expr):
    with slow(note, 'hand edit: %s = %s' % (name, expr)):
        des.userParameters.itemByName(name).expression = expr


def hand_plane(des, name, off, comp=None, after=None):
    # A construction plane made by hand, at the end of the timeline or right after the item named after.
    comp = comp or des.rootComponent
    tl = des.timeline
    opened = open_groups(tl)
    with slow(note, 'hand edit: plane %s' % name):
        if after:
            item(des, after).rollTo(False)
        pi = comp.constructionPlanes.createInput()
        pi.setByOffset(comp.xYConstructionPlane, vi(off))
        p = comp.constructionPlanes.add(pi)
        p.name = name
        tl.moveToEnd()
    close_groups(opened)
    return p


def names(des):
    return [i['name'] for i in H.snapshot(des)['items']]


def index_of(des, name):
    return names(des).index(name)


def short_log(r):
    return [l for l in r['log'] if not l.startswith('  step')]


def kinds(r, name):
    return [t[0] for t in r.get('touched', []) if t[1] == name]


# B. Parameters

@scenario
def b0(S):
    doc, des, r = first(S)
    des.userParameters.add('base_width', vi('41 mm'), 'mm', 'made by hand')
    before = H.snapshot(des)
    v2 = rename_param(variant(), 'base_w', 'base_width')
    r2 = S.run(doc, des, v2, 'rename onto a name made by hand')
    S.expect(not r2['ok'] and 'base_width' in (r2['error'] or '') and 'both' in (r2['error'] or ''), 'a clear error: %s' % r2['error'])
    diff = H.compare(before, H.snapshot(des), fp=True)
    S.expect(not diff, 'nothing lost: %s' % diff[:4])
    S.info['error'] = r2['error']


@scenario
def b1(S):
    doc, des, r = first(S)
    v2 = set_param(variant(), 'extra', '5 mm', 'mm', 'An extra one', True)
    r2 = S.run(doc, des, v2, 'parameter added')
    S.need(r2)
    p = des.userParameters.itemByName('extra')
    S.expect(p is not None and p.comment == 'An extra one' and p.isFavorite and _same(p.expression, '5 mm'),
             'added with its comment and star: %s' % (str((p.expression, p.comment, p.isFavorite)) if p else None))
    S.standard(doc, des, v2, r2)


@scenario
def b2(S):
    doc, des, r = first(S)
    v2 = set_param(variant(), 'base_h', '12 mm')
    r2 = S.run(doc, des, v2, 'value changed')
    S.need(r2)
    S.expect(_same(des.userParameters.itemByName('base_h').expression, '12 mm'), 'set: %s' % des.userParameters.itemByName('base_h').expression)
    S.expect('base_h = 12 mm' in r2['params_set'], 'logged: %s' % r2['params_set'])
    S.standard(doc, des, v2, r2)


@scenario
def b3(S):
    doc, des, r = first(S)
    hand_param(des, 'base_h', '14 mm')
    r2 = S.run(doc, des, variant(), 'after the hand change')
    S.need(r2)
    now = des.userParameters.itemByName('base_h').expression
    S.expect(_same(now, '14 mm'), 'the hand value stays: %s' % now)
    S.expect(any(k.startswith('base_h') for k in r2['params_kept']) and logged(r2, 'parameter kept'), 'reported: %s' % r2['params_kept'])
    S.expect(not r2['params_set'], 'nothing set: %s' % r2['params_set'])
    S.standard(doc, des, variant(), r2, fresh_tweak=lambda d: hand_param(d, 'base_h', '14 mm'))


@scenario
def b4(S):
    doc, des, r = first(S)
    hand_param(des, 'base_h', '14 mm')
    v2 = set_param(variant(), 'base_h', '12 mm')
    r2 = S.run(doc, des, v2, 'a hand change, then the script changes it')
    S.need(r2)
    now = des.userParameters.itemByName('base_h').expression
    S.expect(_same(now, '14 mm'), 'the hand value stays: %s' % now)
    kept = [k for k in r2['params_kept'] if k.startswith('base_h')]
    S.expect(kept and '14 mm' in kept[0] and '12 mm' in kept[0], 'both values reported: %s' % kept)
    S.standard(doc, des, v2, r2, fresh_tweak=lambda d: hand_param(d, 'base_h', '14 mm'))


@scenario
def b5(S):
    doc, des, r = first(S)
    hand_param(des, 'base_h', '14 mm')
    v2 = rename_param(variant(), 'base_h', 'base_height')
    r2 = S.run(doc, des, v2, 'renamed with was=')
    S.need(r2)
    up = des.userParameters
    p = up.itemByName('base_height')
    S.expect(p is not None and up.itemByName('base_h') is None, 'renamed: %s' % [x.name for x in up])
    S.expect(p is not None and _same(p.expression, '14 mm'), 'the hand value carries over: %s' % (p.expression if p else None))
    S.expect('base_height' in up.itemByName('post_h').expression, 'expressions name it: %s' % up.itemByName('post_h').expression)
    rebuilt = [t for t in r2['touched'] if t[0] in ('created', 'replaced') or t[0] == 'updated' and t[1] in SKETCHES]
    S.expect(not rebuilt, 'nothing rebuilt: %s' % rebuilt)
    S.info['touched'] = r2['touched']
    S.standard(doc, des, v2, r2, fresh_tweak=lambda d: hand_param(d, 'base_height', '14 mm'))


def _chain(S, start_at_b):
    doc, des, r = first(S)
    hand_param(des, 'base_h', '14 mm')
    if start_at_b:
        vb = rename_param(variant(), 'base_h', 'base_hb')
        S.need(S.run(doc, des, vb, 'renamed to b'), 'rename to b')
    vc = variant()
    rename_param(vc, 'base_h', 'base_hc', was=['base_h', 'base_hb'])
    vc['rename']['base_hb'] = 'base_hc'
    r2 = S.run(doc, des, vc, 'renamed to c')
    S.need(r2)
    up = des.userParameters
    S.expect(up.itemByName('base_hc') is not None and up.itemByName('base_h') is None and up.itemByName('base_hb') is None,
             'only c is left: %s' % [x.name for x in up])
    p = up.itemByName('base_hc')
    S.expect(p is not None and _same(p.expression, '14 mm'), 'the hand value carries over: %s' % (p.expression if p else None))
    S.info['params_set'] = r2['params_set']
    S.standard(doc, des, vc, r2, fresh_tweak=lambda d: hand_param(d, 'base_hc', '14 mm'))


@scenario
def b6(S):
    _chain(S, False)


@scenario
def b7(S):
    _chain(S, True)


@scenario
def b8(S):
    v1 = set_param(variant(), 'gap', '(base_w-base_d)/2', 'mm', 'Gap')
    doc, des, r = first(S, v1)
    v2 = rename_param(set_param(variant(), 'gap', '(base_w-base_d)/2', 'mm', 'Gap'), 'base_w', 'base_width')
    r2 = S.run(doc, des, v2, 'renamed, Fusion respaces')
    S.need(r2)
    S.info['gap'] = des.userParameters.itemByName('gap').expression
    S.expect(not [k for k in r2['params_kept'] if k.startswith('gap')], 'not flagged as hand-made: %s' % r2['params_kept'])
    S.standard(doc, des, v2, r2)


def only_params(names):
    def describe(b, v):
        for n in names:
            b.param(n, '1 mm', 'mm', 'test')
    return describe


@scenario
def b9(S):
    v1 = set_param(variant(), 'spare', '2 mm', 'mm', 'Spare')
    doc, des, r = first(S, v1)
    r2 = S.run(doc, des, variant(), 'spare dropped')
    S.need(r2)
    S.expect(des.userParameters.itemByName('spare') is None and logged(r2, 'parameter removed: spare'), 'removed: %s' % short_log(r2))
    S.standard(doc, des, variant(), r2)
    # A script that drops all its parameters at once.
    try:
        S.describe = only_params(['p1', 'p2'])
        doc2, des2 = S.tab()
        S.need(S.run(doc2, des2, None, 'two parameters'), 'two parameters')
        S.describe = only_params([])
        r3 = S.run(doc2, des2, None, 'all dropped')
        S.need(r3)
        left = [p.name for p in des2.userParameters]
        S.expect(not left, 'all removed: %s' % left)
    finally:
        S.describe = M.describe


@scenario
def b10(S):
    v1 = set_param(variant(base_dist='base_h + spare'), 'spare', '2 mm', 'mm', 'Spare')
    doc, des, r = first(S, v1)
    r2 = S.run(doc, des, variant(base_dist='base_h + spare'), 'dropped, still used')
    S.need(r2)
    S.expect(des.userParameters.itemByName('spare') is not None and logged(r2, 'parameter spare is no longer in the script'), 'kept and reported: %s' % short_log(r2))
    r3 = S.run(doc, des, variant(), 'no longer used')
    S.need(r3)
    S.expect(des.userParameters.itemByName('spare') is None and logged(r3, 'parameter removed: spare'), 'removed once unused: %s' % short_log(r3))
    S.standard(doc, des, variant(), r3)


@scenario
def b11(S):
    v1 = set_param(variant(), 'spare', '2 mm', 'mm', 'Spare')
    doc, des, r = first(S, v1)
    hand_plane(des, 'Hand plane', 'spare')
    r2 = S.run(doc, des, variant(), 'dropped, a hand plane uses it')
    S.need(r2)
    S.expect(des.userParameters.itemByName('spare') is not None, 'kept: %s' % short_log(r2))
    S.expect(logged(r2, 'parameter spare is no longer in the script'), 'reported: %s' % short_log(r2))
    S.standard(doc, des, variant(), r2, hand=('Hand plane',), ignore={'params': ('spare',)})


@scenario
def b12(S):
    doc, des, r = first(S)
    # base_h, not base_w: a fresh build makes the parameters in order, so a formula can only name
    # the ones above it.
    before = H.snapshot(des)
    v2 = set_param(variant(), 'base_h', 'base_d / 3')
    r2 = S.run(doc, des, v2, 'favorite with a formula')
    S.expect(not r2['ok'] and 'favorite base_h' in (r2['error'] or ''), 'a clear error naming it: %s' % r2['error'])
    diff = H.compare(before, H.snapshot(des), fp=True)
    S.expect(not diff, 'nothing changed before the error: %s' % diff[:4])
    S.info['error'] = r2['error']



@scenario
def b16(S):
    # Many renames at once, with one step's spec changed too. Every mix of the renamed names was
    # tried for each changed step: 21 renames are 2 million fingerprints, and the run hung.
    v1 = variant()
    for i in range(20):
        set_param(v1, 'extra_%02d' % i, '%d mm' % (i + 1), 'mm', 'Unused')
    doc, des, r = first(S, v1)
    v2 = rename_param(variant(), 'base_h', 'base_height')
    for i in range(20):
        set_param(v2, 'extra_%02d_mm' % i, '%d mm' % (i + 1), 'mm', 'Unused')['params'][-1]['was'] = 'extra_%02d' % i
    v2['spec']['post_sketch'] = ('changed',)
    t = time.time()
    r2 = S.run(doc, des, v2, '21 renames and a changed step')
    S.need(r2)
    S.info['seconds'] = round(time.time() - t, 1)
    S.expect(time.time() - t < 120, 'done in under 2 minutes: %.0f s' % (time.time() - t))
    S.expect(kinds(r2, M.LABELS['post_sketch']), 'the changed step reran: %s' % r2['touched'])
    S.info['touched'] = r2['touched']

@scenario
def b13(S):
    doc, des, r = first(S)
    v2 = set_param(variant(), 'hole_d', comment='Hole size', favorite=True)
    r2 = S.run(doc, des, v2, 'comment and star changed')
    S.need(r2)
    p = des.userParameters.itemByName('hole_d')
    S.expect(p.comment == 'Hole size' and p.isFavorite, 'updated in place: %s %s' % (p.comment, p.isFavorite))
    S.expect(any('hole_d' in x and 'favorite' in x for x in r2['params_set']) and any('hole_d comment' in x for x in r2['params_set']),
             'counted as a change, so a saved design saves: %s' % r2['params_set'])
    S.standard(doc, des, v2, r2)


@scenario
def b14(S):
    doc, des, r = first(S)
    v2 = set_param(variant(), 'floor', '2 mm', 'mm', 'A name Fusion keeps')
    r2 = S.run(doc, des, v2, 'refused name')
    S.expect(not r2['ok'] and 'floor' in (r2['error'] or ''), 'a clear error naming it: %s' % r2['error'])
    unchanged_by_refusal(S, r2, 'B14')
    S.info['error'] = r2['error']


@scenario
def b15(S):
    v1 = set_param(variant(), 'tilt', '5 mm', 'mm', 'Tilt')
    doc, des, r = first(S, v1)
    v2 = set_param(variant(), 'tilt', '5 deg', 'deg', 'Tilt')
    r2 = S.run(doc, des, v2, 'unit changed')
    p = des.userParameters.itemByName('tilt')
    S.info['result'] = {'ok': r2['ok'], 'error': r2['error'], 'unit': p.unit if p else None, 'expression': p.expression if p else None}
    set_ok = r2['ok'] and p is not None and p.unit == 'deg'
    refused = not r2['ok'] and 'tilt' in (r2['error'] or '')
    S.expect(set_ok or refused, 'set, or refused naming it; never silent: %s' % S.info['result'])
    unchanged_by_refusal(S, r2, 'B15 unit changed')
    # A parameter the model uses (wall): it can't be made again, so a clear refusal.
    doc3, des3, r3 = first(S)
    v3 = set_param(variant(), 'wall', '3 deg', 'deg')
    r4 = S.run(doc3, des3, v3, 'unit of a used one')
    S.info['used'] = {'ok': r4['ok'], 'error': r4['error']}
    S.expect(r4['ok'] and des3.userParameters.itemByName('wall').unit == 'deg' or not r4['ok'] and 'wall' in (r4['error'] or ''),
             'a used parameter: set, or refused naming it: %s' % S.info['used'])
    unchanged_by_refusal(S, r4, 'B15 used parameter')
    if set_ok:
        S.standard(doc, des, v2, r2)


# C. A step's spec changes

C1_CASES = [
    ('extrude distance', dict(base_dist='base_h + 1 mm'), 'Base extrude'),
    ('extrude symmetric distance', dict(rib_sym='base_d + 2 mm'), 'Rib extrude'),
    ('extrude operation', dict(hole_op=M.JOIN), 'Hole cut'),
    ('extrude profile picker', dict(alt={'hole_cut': 'profile'}), 'Hole cut'),
    ('extrude participants', dict(alt={'hole_cut': 'participants'}), 'Hole cut'),
    ('extrude body name', dict(base_body='Base 2'), 'Base extrude'),
    ('combine target', dict(alt={'rib_join': 'target'}), 'Rib combine'),
    ('combine tools', dict(alt={'rib_join': 'tools'}), 'Rib combine'),
    # Fusion can't switch a combine's operation or a pattern's adjust in place, so those two are made
    # again (F1). Fusion deletes the steps built on a replaced one, and the log must say so.
    ('combine operation', dict(combine_op=M.CUT), 'Rib combine', 'replaced'),
    ('fillet radius', dict(round_r=('round_r / 2', 'round_r')), 'Rounds'),
    ('fillet edges', dict(alt={'round': 'edges'}), 'Rounds'),
    ('chamfer distance', dict(chamfer_d='round_r / 2'), 'Back chamfer'),
    ('chamfer edges', dict(alt={'chamfer': 'edges'}), 'Back chamfer'),
    ('pattern counts', dict(pattern=('hole_n - 1', 'pitch', '1', '1 mm')), 'Hole pattern'),
    ('pattern spacing', dict(pattern=('hole_n', 'pitch * 0.9', '1', '1 mm')), 'Hole pattern'),
    ('pattern adjust', dict(pattern_adjust=True), 'Hole pattern', 'replaced'),
    ('pattern bodies', dict(alt={'hole_pattern': 'bodies'}), 'Hole pattern'),
    ('move x', dict(move=('base_w + 12 mm', '0 mm', '0 mm')), 'Block move'),
    ('move y', dict(move=('base_w + 10 mm', '2 mm', '0 mm')), 'Block move'),
    ('move z', dict(move=('base_w + 10 mm', '0 mm', '3 mm')), 'Block move'),
    ('move bodies', dict(alt={'block_move': 'bodies'}), 'Block move'),
    # Was 'base_h + 1 mm', which floats the post 1 mm over the base. That splits the body, a different
    # test: Fusion then gives the name Base to the post's body, so Rounds and Back chamfer pick edges on
    # the post and the run stops (a fresh build is fine). Open item in the report.
    ('plane offset', dict(top_off='base_h - 1 mm'), 'Top plane'),
    ('plane make', dict(alt={'cap_plane': 'make'}), 'Cap plane'),
]


@scenario
def c1(S):
    # One change at a time, each from version 1 (so the change before is undone in the same run). Every
    # step the run touches must be edited in place, never replaced, except in the cases marked
    # 'replaced'. Those go back to version 1 in a run of their own, so the next case starts clean. After
    # each case the model must be
    # healthy and match a fresh build of the same version, shape and values alike (F41): a step logged
    # "updated" that changed nothing differs from the fresh build.
    doc, des, r = first(S)
    cases = {}
    v = r2 = None
    for what, knobs, name, *kind in C1_CASES:
        kind = kind[0] if kind else 'updated'
        v = variant(**knobs)
        r2 = S.run(doc, des, v, what.replace(' ', '-'))
        # A replaced step takes the steps built on it, and they are made again: logged as replaced, with why.
        bad = [t for t in r2.get('touched', []) if t[0] != 'updated' and not (kind == 'replaced' and (t[1] == name or 'deleted along with ' + name in t[2]))]
        snap = H.snapshot(des)
        cases[what] = {'ok': r2['ok'], 'error': r2['error'], 'kinds': kinds(r2, name), 'other': [t for t in r2.get('touched', []) if t[1] != name], 'health': H.health(snap)}
        S.expect(r2['ok'], '%s: the run failed: %s' % (what, r2['error']))
        S.expect(kinds(r2, name) == [kind], '%s: %s is %s: %s' % (what, name, kind, kinds(r2, name)))
        S.expect(not bad, '%s: nothing else replaced or made: %s' % (what, bad))
        if r2['ok']:
            for line in H.health(snap):
                S.fail('%s: not healthy: %s' % (what, line))
            fdoc, fdes = S.tab()
            fr = S.run(fdoc, fdes, v, what.replace(' ', '-') + '-fresh')
            diff = H.compare(snap, H.snapshot(fdes)) + H.same_readings(des.unitsManager, r2.get('readings', {}), fr.get('readings', {}))
            if not fr['ok']:
                diff.insert(0, 'the fresh build failed: %s' % fr['error'])
            for line in diff:
                S.fail('%s: not the same as a fresh build: %s' % (what, line))
            cases[what]['fresh_diff'] = diff
            H.close_tab(fdoc, note)
            doc.activate()
        if not r2['ok']:
            doc, des = S.tab()  # A broken tab: start again in a new one (§ 6).
            S.need(S.run(doc, des, variant(), 'v1 again'), 'version 1 again')
        elif kind == 'replaced':
            S.need(S.run(doc, des, variant(), what.replace(' ', '-') + '-back'), 'version 1 again')
    S.info['cases'] = cases
    S.standard(doc, des, v, r2)


@scenario
def c2(S):
    doc, des, r = first(S)
    v2 = variant(base_draw=M.base_outline_v2)
    r2 = S.run(doc, des, v2, 'draw changed')
    S.need(r2)
    S.expect('updated' in kinds(r2, 'Base outline'), 'the sketch is redrawn: %s' % r2['touched'])
    S.expect('updated' in kinds(r2, 'Base extrude'), 'its extrude is repointed: %s' % r2['touched'])
    S.expect(not [n for n in names(des) if '(old)' in n], 'the old sketch is gone: %s' % names(des))
    S.standard(doc, des, v2, r2)


POST_A = 'def post_rect(width, depth):\n    def draw(s):\n        return rectangle(width, depth)(s)\n    return draw\n'
POST_B = ('def post_rect(width, depth):\n    # The post, a square.\n\n    def draw(s):\n        # Same as before, a comment and a\n'
          '        # blank line added.\n\n        return rectangle(width, depth)(s)\n    return draw\n')


@scenario
def c5(S):
    v1 = variant(post_draw=M.make_fn(POST_A, 'post_rect'))
    doc, des, r = first(S, v1)
    v2 = variant(post_draw=M.make_fn(POST_B, 'post_rect'))
    r2 = S.run(doc, des, v2, 'comments only')
    S.need(r2)
    S.expect(not H.changed(r2), 'nothing reruns: %s' % r2['touched'])
    S.standard(doc, des, v2, r2)


@scenario
def c6(S):
    doc, des, r = first(S)
    v2 = variant(uses={'post': ('base', 'top_plane')})
    r2 = S.run(doc, des, v2, 'uses changed')
    S.need(r2)
    S.expect(kinds(r2, 'Post join'), 'the step reruns: %s' % r2['touched'])
    S.standard(doc, des, v2, r2)


@scenario
def c7(S):
    doc, des, r = first(S)
    v2 = variant(base_dist='base_h + 1 mm')
    r2 = S.run(doc, des, v2, 'base changed')
    S.need(r2)
    want = ['Base extrude', 'Hole cut', 'Hole pattern', 'Post join', 'Rib combine', 'Rounds', 'Back chamfer']
    missing = [n for n in want if not kinds(r2, n)]
    S.expect(not missing, 'the steps that use it rerun, and theirs: missing %s' % missing)
    S.info['touched'] = r2['touched']
    S.standard(doc, des, v2, r2)


# D. Sketch redraws

POST_C = ('def post_rect(width, depth):\n    def draw(s):\n        lines = s.sketchCurves.sketchLines.addTwoPointRectangle(point(0, 0), point(1, 1))\n'
          '        gc = s.geometricConstraints\n        gc.addCoincident(lines.item(0).startSketchPoint, s.originPoint)\n'
          '        for i in (0, 2):\n            gc.addHorizontal(lines.item(i))\n        for i in (1, 3):\n            gc.addVertical(lines.item(i))\n'
          '        dims = s.sketchDimensions\n'
          '        dims.addDistanceDimension(lines.item(1).startSketchPoint, lines.item(1).endSketchPoint, V, point(2, 0.5)).parameter.expression = depth\n'
          '        dims.addDistanceDimension(lines.item(0).startSketchPoint, lines.item(0).endSketchPoint, H, point(0.5, -1)).parameter.expression = width\n'
          '        return lines\n    return draw\n')


def old_items(des):
    return [n for n in names(des) if '(old)' in n]


def sketch_count(des):
    return len([i for i in H.snapshot(des)['items'] if i['type'] == 'Sketch'])


@scenario
def d1(S):
    doc, des, r = first(S)
    n = sketch_count(des)
    v2 = variant(post_draw=M.make_fn(POST_C, 'post_rect'))
    r2 = S.run(doc, des, v2, 'post redrawn')
    S.need(r2)
    S.expect(kinds(r2, 'Post outline') == ['updated'] and kinds(r2, 'Post join') == ['updated'], 'redrawn and repointed: %s' % r2['touched'])
    S.expect(not old_items(des) and sketch_count(des) == n, 'the old sketch is gone: %s, %d sketches, %d before' % (old_items(des), sketch_count(des), n))
    post = item(des, 'Post join').entity
    S.expect(post.profile.parentSketch.name == 'Post outline', 'the extrude uses the new sketch: %s' % post.profile.parentSketch.name)
    S.standard(doc, des, v2, r2)


@scenario
def d2(S):
    doc, des, r = first(S)
    v2 = variant(base_draw=M.base_outline_v2)
    r2 = S.run(doc, des, v2, 'base redrawn')
    S.need(r2)
    S.expect('updated' in kinds(r2, 'Corner mark'), 'the sketch projecting from it is redone: %s' % r2['touched'])
    mark = item(des, 'Corner mark')
    S.expect(mark is not None and mark.healthState == cad_apprentice.Healthy, 'the mark is healthy: %s' % (mark.healthState if mark else None))
    try:
        cad_apprentice.tagged(keyed(des, 'base_sketch').entity, 'corner')
        found = True
    except Exception:
        found = False
    S.expect(found, 'the tag is on the new sketch')
    S.expect(not old_items(des), 'no old sketch left: %s' % old_items(des))
    S.standard(doc, des, v2, r2)


@scenario
def d4(S):
    doc, des, r = first(S)
    v2 = variant(spec={'block_sketch': ('redraw',)})
    r2 = S.run(doc, des, v2, 'inner sketch redrawn')
    S.need(r2)
    sk = keyed(des, 'block_sketch')
    S.expect(sk is not None and sk.entity.parentComponent.name == 'Inner', 'it stays in Inner: %s' % (sk.entity.parentComponent.name if sk else None))
    S.expect(kinds(r2, 'Block outline') == ['updated'], 'redrawn: %s' % r2['touched'])
    S.expect(not old_items(des), 'no old sketch left: %s' % old_items(des))
    S.standard(doc, des, v2, r2)


@scenario
def d5(S):
    doc, des, r = first(S)
    v2 = variant(spec={'base_sketch': ('redraw',), 'post_sketch': ('redraw',), 'mark_sketch': ('redraw',), 'hole_sketch': ('redraw',)})
    r2 = S.run(doc, des, v2, 'four redrawn')
    S.need(r2)
    S.expect(not old_items(des), 'all old sketches are gone: %s' % old_items(des))
    bad = [l for l in r2['log'] if 'could not' in l or 'WARNING' in l or 'BROKEN' in l]
    S.expect(not bad, 'no errors: %s' % bad)
    S.standard(doc, des, v2, r2)


@scenario
def d7(S):
    # The post sketch moves to the XY plane under the same key, with the same uses. Before, the
    # plane wasn't checked, so it stayed on the top plane until the key changed.
    doc, des, r = first(S)
    v2 = variant(alt={'post_sketch': 'on_xy'})
    r2 = S.run(doc, des, v2, 'other plane')
    S.need(r2)
    S.info['touched'] = touched(r2)
    S.expect(any(t[1] == 'Post outline' and 'another plane' in t[2] for t in touched(r2)), 'the post sketch is redrawn: %s' % touched(r2))
    it = keyed(des, 'post_sketch')
    on = it.entity.referencePlane.name if it else None
    S.expect(on == 'XY', 'it sits on the XY plane: %s' % on)
    S.standard(doc, des, v2, r2)


@scenario
def d6(S):
    doc, des, r = first(S)
    v2 = variant(spec={'post_sketch': ('redraw',)}, die_at='post_sketch')
    r2 = S.run(doc, des, v2, 'dies mid-redraw')
    S.expect(not r2['ok'] and logged(r2, 'STOPPED'), 'it stops and says so: %s' % short_log(r2)[-4:])
    S.info['left'] = old_items(des)
    v3 = variant(spec={'post_sketch': ('redraw',)})
    r3 = S.run(doc, des, v3, 'next run')
    S.need(r3)
    S.expect(not old_items(des), 'the next run cleans up: %s' % old_items(des))
    S.standard(doc, des, v3, r3)


# E. Order and reorder

def group_of(des, name):
    for i in H.snapshot(des)['items']:
        if i['name'] == name:
            return i['group']
    return 'missing'


def _moved(S, v2, label, collapse=False, hand_after=None):
    doc, des, r = first(S)
    hand = ()
    if hand_after:
        hand_plane(des, 'Hand plane', '7 mm', after=hand_after)
        hand = ('Hand plane',)
    tl = des.timeline
    if collapse:
        opened = open_groups(tl)
        for g in tl.timelineGroups:
            g.isCollapsed = True
    r2 = S.run(doc, des, v2, label)
    S.need(r2)
    S.expect(not touched(r2, 'replaced') and not touched(r2, 'created'), 'nothing rebuilt: %s' % touched(r2))
    S.expect(bool(moves(r2)), 'the log lists the move')
    S.expect(order_of(des, v2['order']) == [k for k in v2['order'] if isinstance(k, str)], 'timeline order is the script order: %s' % order_of(des, v2['order']))
    S.info['moves'] = moves(r2)
    S.info['touched'] = touched(r2)
    if collapse:
        now = {g.name: g.isCollapsed for g in tl.timelineGroups}
        S.expect(all(now.values()), 'the groups are collapsed again: %s' % now)
    if hand_after:
        it = item(des, 'Hand plane')
        S.expect(it is not None and it.healthState == cad_apprentice.Healthy, 'the hand plane is healthy')
        S.info['order'] = names(des)
    return doc, des, r2, hand


@scenario
def e1(S):
    v2 = variant(order=reordered(M.ORDER, ['top_plane'], 'hole_pattern'))
    doc, des, r2, hand = _moved(S, v2, 'moved later')
    S.standard(doc, des, v2, r2)


@scenario
def e2(S):
    v2 = variant(order=reordered(M.ORDER, ['rib_sketch'], 'top_plane'))
    doc, des, r2, hand = _moved(S, v2, 'moved earlier')
    S.standard(doc, des, v2, r2)


@scenario
def e5(S):
    # The post sketch moves before the top plane it sits on; the script now puts it on the XY plane.
    # Fusion can't move it there, so it must be made again at its new spot, with nothing after it lost.
    doc, des, r = first(S)
    v2 = variant(alt={'post_sketch': 'on_xy'}, uses={'post_sketch': ()}, order=reordered(M.ORDER, ['post_sketch'], 'base'))
    r2 = S.run(doc, des, v2, 'move Fusion refuses')
    S.info['run2'] = {k: r2.get(k) for k in ('ok', 'error', 'touched')}
    S.info['log'] = short_log(r2)
    S.expect(r2['ok'] or 'by hand' in (r2['error'] or '') or 'could' in (r2['error'] or ''), 'it finishes, or a clear refusal: %s' % r2['error'])
    S.expect(not logged(r2, 'deleted with'), 'no quiet loss: %s' % [l for l in r2['log'] if 'deleted with' in l])
    if r2['ok']:
        S.expect(order_of(des, v2['order']) == v2['order'], 'timeline order is the script order: %s' % order_of(des, v2['order']))
        S.standard(doc, des, v2, r2)


@scenario
def e6(S):
    v2 = variant(order=reordered(M.ORDER, ['mark_sketch'], 'round'))
    doc, des, r2, hand = _moved(S, v2, 'swapped')
    S.standard(doc, des, v2, r2)


@scenario
def e7(S):
    rest = [k for k in M.ORDER[3:] if k not in ('hole_sketch', 'hole_cut', 'hole_pattern', 'post_sketch', 'post')]
    v1 = variant(order=M.ORDER[:3] + [('group', 'Holes', ['hole_sketch', 'hole_cut', 'hole_pattern']), ('group', 'Post', ['post_sketch', 'post'])] + rest)
    doc, des, r = first(S, v1)
    v2 = variant(order=M.ORDER[:3] + [('group', 'Holes', ['hole_sketch', 'hole_cut']), ('group', 'Post', ['hole_pattern', 'post_sketch', 'post'])] + rest)
    r2 = S.run(doc, des, v2, 'to the other group')
    S.need(r2)
    g = group_of(des, 'Hole pattern')
    S.expect(g and 'Post' in g, 'Hole pattern is in the Post group: %s' % g)
    S.expect('Holes' in (group_of(des, 'Hole cut') or ''), 'Hole cut stays in Holes: %s' % group_of(des, 'Hole cut'))
    S.expect(not touched(r2, 'replaced') and not touched(r2, 'created'), 'nothing rebuilt: %s' % touched(r2))
    S.standard(doc, des, v2, r2)


@scenario
def e8(S):
    v2 = variant(order=reordered(M.ORDER, ['top_plane'], 'hole_pattern'))
    doc, des, r2, hand = _moved(S, v2, 'moved past the hand plane', hand_after='Hole cut')
    S.standard(doc, des, v2, r2, hand=hand)


@scenario
def e9(S):
    v2 = variant(order=reordered(M.ORDER, ['rib_sketch'], 'top_plane'))
    doc, des, r2, hand = _moved(S, v2, 'moved, groups collapsed', collapse=True)
    S.standard(doc, des, v2, r2)


@scenario
def e10(S):
    doc, des, r = first(S)
    before = H.snapshot(des)
    v2 = variant(order=[k for k in M.ORDER if k != 'mark_sketch'], inner_order=M.INNER + ['mark_sketch'])
    r2 = S.run(doc, des, v2, 'into another component')
    S.expect(not r2['ok'] and 'by hand' in (r2['error'] or ''), 'refused: %s' % r2['error'])
    S.info['error'] = r2['error']
    lost = [i['name'] for i in before['items'] if i['name'] not in names(des)]
    S.expect(not lost, 'nothing lost: %s' % lost)


@scenario
def e11(S):
    v1 = variant(cap_order=['solo_plane'] + M.CAP)
    doc, des, r = first(S, v1)
    v2 = variant(cap_order=M.CAP + ['solo_plane'])
    r2 = S.run(doc, des, v2, 'to the very end')
    S.need(r2)
    S.expect(any(l.startswith('moved Solo plane') for l in r2['log']), 'moved: %s' % moves(r2))
    S.expect(not touched(r2, 'replaced') and not touched(r2, 'created'), 'nothing rebuilt: %s' % touched(r2))
    S.expect(names(des)[-1] == 'Solo plane', 'it is last: %s' % names(des)[-3:])
    S.standard(doc, des, v2, r2)


@scenario
def e12(S):
    doc, des, r = first(S)
    order = reordered(reordered(M.ORDER, ['rib_sketch', 'rib', 'rib_join'], 'top_plane'), ['mark_sketch'], 'round')
    v2 = variant(order=order, inner_order=['block_sketch', 'block', 'stock', 'block_move'],
                 names={'base': 'Base, v2', 'rib': 'Rib, v2', 'rib_join': 'Rib join, v2', 'mark_sketch': 'Mark, v2', 'stock': 'Stock, v2', 'cap': 'Cap, v2'})
    r2 = S.run(doc, des, v2, 'renames and moves')
    S.need(r2)
    S.expect(not touched(r2, 'replaced') and not touched(r2, 'created'), 'nothing rebuilt: %s' % touched(r2))
    S.info['moves'] = moves(r2)
    S.info['log'] = short_log(r2)
    S.standard(doc, des, v2, r2)


# F. Adding and removing steps

def groups(des):
    return {g.name: g.isCollapsed for g in des.timeline.timelineGroups}


def members(des, group):
    return [i['name'] for i in H.snapshot(des)['items'] if i['group'] == group]


@scenario
def f1(S):
    doc, des, r = first(S)
    v2 = variant(order=reordered(M.ORDER + ['mid_plane'], ['mid_plane'], 'top_plane'))
    r2 = S.run(doc, des, v2, 'a plane added in the middle')
    S.need(r2)
    S.expect(touched(r2) == [('created', 'Middle plane', 'new')], 'only the new step is made: %s' % touched(r2))
    S.expect(index_of(des, 'Middle plane') == index_of(des, 'Top plane') + 1, 'it lands right after Top plane: %s' % names(des)[:6])
    S.standard(doc, des, v2, r2)


@scenario
def f2(S):
    doc, des, r = first(S)
    v2 = variant(top_first=['first_plane'])
    r2 = S.run(doc, des, v2, 'a plane added at the start')
    S.need(r2)
    S.expect(touched(r2) == [('created', 'First plane', 'new')], 'only the new step is made: %s' % touched(r2))
    S.expect(names(des)[0] == 'First plane', 'it is first: %s' % names(des)[:3])
    S.standard(doc, des, v2, r2)


@scenario
def f3(S):
    doc, des, r = first(S)
    gone = ['hole_sketch', 'hole_cut', 'hole_pattern']
    v2 = variant(order=[k for k in M.ORDER if k not in gone])
    r2 = S.run(doc, des, v2, 'the holes removed')
    S.need(r2)
    S.expect(sorted(t[1] for t in touched(r2, 'removed')) == sorted(M.LABELS[k] for k in gone), 'the three steps go: %s' % touched(r2))
    S.expect(not touched(r2, 'replaced') and not touched(r2, 'created'), 'nothing rebuilt: %s' % touched(r2))
    S.standard(doc, des, v2, r2)


@scenario
def f5(S):
    doc, des, r = first(S)
    v2 = variant(with_inner=False)
    r2 = S.run(doc, des, v2, 'the inner component removed')
    S.need(r2)
    tree = H.snapshot(des)['tree']
    S.expect(not any(c['comp'] == 'Inner' for o in tree for c in o['children']), 'the occurrence goes: %s' % tree)
    S.expect(not any(k in [i['key'] for i in H.snapshot(des)['items']] for k in M.INNER), 'its steps go')
    S.info['touched'] = touched(r2)
    S.standard(doc, des, v2, r2)


@scenario
def f6(S):
    # A step asks for the rib's body after the combine took it: what an old key reused for something
    # else looks like. body() names the step and says what to do.
    doc, des, r = first(S)
    before = names(des)
    v2 = variant(order=reordered(M.ORDER + ['rib_peek'], ['rib_peek'], 'rib_join'))
    r2 = S.run(doc, des, v2, 'asks for a body that is gone')
    S.expect(not r2['ok'] and 'has no body' in (r2['error'] or '') and 'new key' in (r2['error'] or ''), 'the clear message: %s' % r2['error'])
    S.info['error'] = r2['error']
    S.expect(names(des) == before, 'nothing changed: %s' % names(des))


# G. Replace, and what depends on it

@scenario
def g1(S):
    doc, des, r = first(S, variant(cap_order=M.CAP + ['solo_plane']))
    v2 = variant(cap_order=M.CAP + ['solo_plane'], spec={'solo_plane': ('v2',)})
    r2 = S.run(doc, des, v2, 'the last step replaced')
    S.need(r2)
    S.expect(kinds(r2, 'Solo plane') == ['replaced'], 'replaced: %s' % touched(r2))
    S.expect(names(des)[-1] == 'Solo plane', 'still last: %s' % names(des)[-3:])
    S.standard(doc, des, v2, r2)


@scenario
def g3(S):
    doc, des, r = first(S, variant(cap_order=M.CAP + ['solo_plane']))
    hand_plane(des, 'Hand plane', '7 mm')
    before = names(des)
    v2 = variant(cap_order=M.CAP + ['solo_plane'], spec={'solo_plane': ('v2',)})
    r2 = S.run(doc, des, v2, 'replace with a hand plane after it')
    S.expect(not r2['ok'] and 'Hand plane' in (r2['error'] or ''), 'refused, naming the hand plane: %s' % r2['error'])
    S.info['error'] = r2['error']
    S.expect(names(des) == before, 'nothing lost: %s' % names(des))
    it = item(des, 'Hand plane')
    S.expect(it is not None and it.healthState == cad_apprentice.Healthy, 'the hand plane is healthy')


@scenario
def g5(S):
    # The combine's tools are written another way but are the same body: Fusion refused to be given the
    # same bodies again, which turned into a replace (fixed).
    doc, des, r = first(S)
    v2 = variant(alt={'rib_join': 'tools'})
    r2 = S.run(doc, des, v2, 'same bodies, new code')
    S.need(r2)
    S.expect(kinds(r2, 'Rib combine') == ['updated'], 'edited in place: %s' % touched(r2))
    S.expect(not touched(r2, 'replaced'), 'no replace: %s' % touched(r2))
    S.expect(not logged(r2, 'could not edit'), 'no refused edit: %s' % [l for l in r2['log'] if 'could not' in l])
    S.standard(doc, des, v2, r2)


# H. Groups

def grouped(order, name, keys):
    # order with keys (next to each other in it) put in a group called name.
    i = order.index(keys[0])
    return order[:i] + [('group', name, list(keys))] + [k for k in order[i:] if k not in keys]


@scenario
def h1(S):
    doc, des, r = first(S)
    snap = H.snapshot(des)
    S.info['groups'] = snap['groups']
    S.info['items'] = [(i['name'], i['group']) for i in snap['items']]
    for comp, keys in (('Outer', M.ORDER), ('Inner', M.INNER)):
        wrong = [i['name'] for i in snap['items'] if i['key'] in keys and i['group'] != comp]
        S.expect(not wrong, 'the %s steps are in group %s: %s' % (comp, comp, wrong))
    S.standard(doc, des, variant(), r, fresh=False)


@scenario
def h2(S):
    v = variant(order=grouped(M.ORDER, 'Post', ['post_sketch', 'post']))
    doc, des, r = first(S, v)
    S.info['groups'] = groups(des)
    S.expect(members(des, 'Outer · Post') == ['Post outline', 'Post join'], 'group "Outer · Post": %s' % groups(des))
    S.standard(doc, des, v, r, fresh=False)


@scenario
def h3(S):
    # Loose steps of the component between its groups.
    order = grouped(grouped(M.ORDER, 'A', ['base_sketch', 'base']), 'B', ['hole_sketch', 'hole_cut', 'hole_pattern'])
    v = variant(order=order)
    doc, des, r = first(S, v)
    g = groups(des)
    S.info['groups'] = g
    S.info['log'] = short_log(r)
    S.expect('Outer · A' in g and 'Outer · B' in g, 'both inner groups: %s' % g)
    S.expect('Outer' in g or any('Outer' in l and 'group' in l for l in r['log']), 'Outer is grouped, or the log says why not: %s' % short_log(r))
    S.standard(doc, des, v, r)


@scenario
def h4(S):
    v1 = variant(order=grouped(grouped(M.ORDER, 'A', ['base_sketch', 'base', 'top_plane']), 'B', ['hole_sketch', 'hole_cut', 'hole_pattern']))
    doc, des, r = first(S, v1)
    v2 = variant(order=grouped(grouped(M.ORDER, 'A', ['base_sketch', 'base']), 'B', ['top_plane', 'hole_sketch', 'hole_cut', 'hole_pattern']))
    r2 = S.run(doc, des, v2, 'top plane into group B')
    S.need(r2)
    S.expect(members(des, 'Outer · A') == ['Base outline', 'Base extrude'], 'group A: %s' % members(des, 'Outer · A'))
    S.expect(members(des, 'Outer · B') == ['Top plane', 'Hole outline', 'Hole cut', 'Hole pattern'], 'group B: %s' % members(des, 'Outer · B'))
    S.expect(not changed_steps(r2), 'no step touched: %s' % touched(r2))
    S.standard(doc, des, v2, r2)


def changed_steps(r):
    return [t for t in r.get('touched', []) if t[0] in ('created', 'updated', 'replaced', 'removed')]


@scenario
def h5(S):
    v1 = variant(order=grouped(M.ORDER, 'Holes', ['hole_sketch', 'hole_cut', 'hole_pattern']))
    doc, des, r = first(S, v1)
    v2 = variant(order=grouped(M.ORDER, 'Drills', ['hole_sketch', 'hole_cut', 'hole_pattern']))
    r2 = S.run(doc, des, v2, 'group renamed')
    S.need(r2)
    g = groups(des)
    S.expect('Outer · Drills' in g and 'Outer · Holes' not in g, 'renamed: %s' % g)
    S.expect(members(des, 'Outer · Drills') == ['Hole outline', 'Hole cut', 'Hole pattern'], 'same steps: %s' % members(des, 'Outer · Drills'))
    S.expect(not changed_steps(r2), 'no step touched: %s' % touched(r2))
    S.standard(doc, des, v2, r2)


@scenario
def h6(S):
    v1 = variant(order=grouped(M.ORDER, 'Holes', ['hole_sketch', 'hole_cut', 'hole_pattern']))
    doc, des, r = first(S, v1)
    v2 = variant()
    r2 = S.run(doc, des, v2, 'group dropped')
    S.need(r2)
    g = groups(des)
    S.expect('Outer · Holes' not in g, 'the group goes: %s' % g)
    S.expect(all(n in names(des) for n in ('Hole outline', 'Hole cut', 'Hole pattern')), 'its steps stay')
    S.expect(not changed_steps(r2), 'no step touched: %s' % touched(r2))
    S.standard(doc, des, v2, r2)


@scenario
def h7(S):
    # One group is collapsed by hand and the rest opened. A run that regroups (a step added to the collapsed one)
    # leaves each the way it was.
    v1 = variant(order=grouped(M.ORDER, 'Holes', ['hole_sketch', 'hole_cut', 'hole_pattern']))
    doc, des, r = first(S, v1)
    for g in des.timeline.timelineGroups:
        g.isCollapsed = False
    for g in des.timeline.timelineGroups:
        if g.name == 'Outer · Holes':
            g.isCollapsed = True
    want = groups(des)
    v2 = variant(order=grouped(M.ORDER + ['mid_plane'], 'Holes', ['hole_sketch', 'hole_cut', 'hole_pattern', 'mid_plane']))
    v2['order'] = [k for k in v2['order'] if k != 'mid_plane']
    r2 = S.run(doc, des, v2, 'a step added to the collapsed group')
    S.need(r2)
    S.expect(members(des, 'Outer · Holes')[-1:] == ['Middle plane'], 'the group took the new step: %s' % members(des, 'Outer · Holes'))
    S.expect(groups(des) == want, 'as they were left: %s, was %s' % (groups(des), want))
    S.standard(doc, des, v2, r2)


@scenario
def h8(S):
    doc, des, r = first(S)
    hand_plane(des, 'Hand 1', '7 mm')
    hand_plane(des, 'Hand 2', '8 mm')
    tl = des.timeline
    tl.timelineGroups.add(tl.count - 2, tl.count - 1).name = 'Hand group'
    v2 = variant(order=reordered(M.ORDER + ['mid_plane'], ['mid_plane'], 'top_plane'))
    r2 = S.run(doc, des, v2, 'a run that regroups')
    S.need(r2)
    S.expect(members(des, 'Hand group') == ['Hand 1', 'Hand 2'], 'the hand group is left alone: %s' % members(des, 'Hand group'))
    S.standard(doc, des, v2, r2, hand=('Hand 1', 'Hand 2'), ignore={'groups': ('Hand group',)})


@scenario
def h9(S):
    v = variant(order=grouped(M.ORDER, 'Solo', ['top_plane']))
    doc, des, r = first(S, v)
    S.expect('Outer · Solo' not in groups(des), 'no group of one: %s' % groups(des))
    S.expect(not logged(r, 'could not group'), 'no error: %s' % [l for l in r['log'] if 'group' in l])
    S.standard(doc, des, v, r)


@scenario
def h11(S):
    doc, des, r = first(S)
    for g in des.timeline.timelineGroups:
        g.isCollapsed = g.name != 'Outer'
    want = groups(des)
    r2 = S.run(doc, des, variant(), 'rerun')
    S.need(r2)
    S.expect(groups(des) == want, 'the groups are as they were left: %s, was %s' % (groups(des), want))
    S.expect(not any('group' in l.lower() for l in short_log(r2)), 'no group lines: %s' % [l for l in r2['log'] if 'group' in l.lower()])


# I. Components

def occurrences_of(des, comp_name):
    for c in des.allComponents:
        if c.name == comp_name:
            return des.rootComponent.allOccurrencesByComponent(c).count
    return 0


@scenario
def i2(S):
    doc, des, r = first(S)
    v2 = variant(names={'outer': 'Outer, v2'})
    r2 = S.run(doc, des, v2, 'component renamed')
    S.need(r2)
    S.expect(any(c.name == 'Outer, v2' for c in des.allComponents), 'the component has the new name: %s' % [c.name for c in des.allComponents])
    S.expect(not changed_steps(r2), 'nothing rebuilt: %s' % touched(r2))
    S.info['groups'] = groups(des)
    S.standard(doc, des, v2, r2)


@scenario
def i3(S):
    # A Part design can't hold subcomponents: everything goes in the top component, and the log says so.
    doc, des = S.tab()
    des.designIntent = adsk.fusion.DesignIntentTypes.PartDesignIntentType
    r = S.run(doc, des, variant(), 'part design')
    S.need(r)
    S.expect(des.rootComponent.occurrences.count == 0, 'no occurrences: %d' % des.rootComponent.occurrences.count)
    S.expect(logged(r, 'a part design has no subcomponents'), 'the log says so: %s' % short_log(r))
    S.info['log'] = short_log(r)
    S.standard(doc, des, variant(), r, fresh=False)


@scenario
def i4(S):
    v1 = variant(inner_copies=('2', 'base_w + 20 mm'))
    doc, des, r = first(S, v1)
    S.expect(occurrences_of(des, 'Inner') == 2, 'two copies: %d' % occurrences_of(des, 'Inner'))
    v2 = variant(inner_copies=('3', 'base_w + 30 mm'))
    r2 = S.run(doc, des, v2, 'count and spacing changed')
    S.need(r2)
    S.expect(occurrences_of(des, 'Inner') == 3, 'three copies: %d' % occurrences_of(des, 'Inner'))
    S.expect(kinds(r2, 'Inner copies') == ['updated'], 'edited in place: %s' % touched(r2))
    S.standard(doc, des, v2, r2)


# J. Hand edits to the script's features

def hand_rename(des, key, name):
    keyed(des, key).entity.name = name


@scenario
def j1(S):
    doc, des, r = first(S)
    hand_rename(des, 'base', 'Hand base')
    r2 = S.run(doc, des, variant(), 'after the hand rename')
    S.need(r2)
    S.expect(keyed(des, 'base').name == 'Hand base', 'the hand name stays: %s' % keyed(des, 'base').name)
    S.expect(any('Hand base' in l and 'by hand' in l for l in r2['log']), 'the run reports it: %s' % short_log(r2))
    S.expect(not changed_steps(r2), 'nothing rebuilt: %s' % touched(r2))
    S.standard(doc, des, variant(), r2, fresh_tweak=lambda fdes: hand_rename(fdes, 'base', 'Hand base'))


@scenario
def j3(S):
    doc, des, r = first(S)
    opened = open_groups(des.timeline)
    with slow(note, 'hand edit: delete the chamfer'):
        keyed(des, 'chamfer').entity.deleteMe()
    close_groups(opened)
    r2 = S.run(doc, des, variant(), 'after the chamfer is deleted by hand')
    S.need(r2)
    S.expect(kinds(r2, 'Back chamfer') == ['created'], 'made again: %s' % touched(r2))
    S.standard(doc, des, variant(), r2)


@scenario
def j4(S):
    doc, des, r = first(S)
    opened = open_groups(des.timeline)
    with slow(note, 'hand edit: suppress the chamfer'):
        keyed(des, 'chamfer').isSuppressed = True
    close_groups(opened)
    r2 = S.run(doc, des, variant(), 'after the chamfer is suppressed by hand')
    S.need(r2)
    S.expect(keyed(des, 'chamfer').isSuppressed, 'still suppressed')
    S.expect(any('Back chamfer' in l and 'suppress' in l for l in r2['log']), 'the run reports it: %s' % short_log(r2))
    S.info['log'] = short_log(r2)


@scenario
def j5(S):
    doc, des, r = first(S)
    hand_plane(des, 'Hand between', '6 mm', after='Top plane')
    hand_plane(des, 'Hand after', '7 mm')
    r2 = S.run(doc, des, variant(), 'rerun with hand planes')
    S.need(r2)
    S.expect(not changed_steps(r2), 'nothing rebuilt: %s' % touched(r2))
    v3 = set_param(variant(), 'base_h', '12 mm')
    r3 = S.run(doc, des, v3, 'a parameter change with hand planes')
    S.need(r3)
    S.info['order'] = names(des)
    S.standard(doc, des, v3, r3, hand=('Hand between', 'Hand after'))


@scenario
def j6(S):
    # take_over (F49): a feature the library didn't make is tagged by the script, and the run accepts it
    # as it is. Here the base extrude loses its marks and name, so it looks made by hand.
    v = variant()
    doc, des, r = first(S, v)
    ent = keyed(des, 'base').entity
    for a in [a for a in ent.attributes if a.groupName == cad_apprentice.GROUP]:
        a.deleteMe()
    ent.name = 'Hand base'
    want = M.label(v, 'base')

    def taking_over(b, v):
        b.take_over('base', want, ent)
        M.describe(b, v)
    S.describe = taking_over
    try:
        r2 = S.run(doc, des, v, 'taken over')
    finally:
        S.describe = M.describe
    S.need(r2)
    S.expect(not H.changed(r2) and not r2['params_set'], 'nothing rebuilt: %s' % touched(r2))
    S.expect(ent.isValid and ent.name == want, "the same feature, under the script's name: %s" % (ent.name if ent.isValid else 'gone'))
    S.expect(ent.isValid and _attr(ent, 'key') == 'base' and bool(_attr(ent, 'fp')), 'it is tracked now')
    S.standard(doc, des, v, r2)


# L. Parameter trials: a value changed in the Parameters dialog, then put back, the way a design's
# check_params does it.

def trial(des, name, expr):
    # Sets the value, reads the health, puts the old value back. Returns the problems seen.
    p = des.userParameters.itemByName(name)
    old = p.expression
    try:
        with slow(note, 'trial %s = %s' % (name, expr)):
            p.expression = expr
            adsk.doEvents()
        bad = H.health(H.snapshot(des))
    except Exception as err:
        bad = ['refused: %s' % str(err).split(' - ')[-1].strip()]
    with slow(note, 'put %s back to %s' % (name, old)):
        p.expression = old
        adsk.doEvents()
    return bad


def halves_and_doubles(des, names):
    out = []
    for n in names:
        v = des.userParameters.itemByName(n).value * 10  # cm to mm
        out += [(n, '%g mm' % (v / 2)), (n, '%g mm' % (v * 2))]
    return out


@scenario
def l1(S):
    doc, des, r = first(S)
    favorites = [p[0] for p in M.PARAMS if p[4]]
    seen = {}
    for name, expr in halves_and_doubles(des, favorites):
        bad = trial(des, name, expr)
        seen['%s = %s' % (name, expr)] = bad or 'ok'
        S.expect(not bad, '%s = %s: %s' % (name, expr, bad))
    S.info['trials'] = seen


@scenario
def l2(S):
    # Each trial is put back and the design must match what it was. The last trial lifts the top
    # plane 1 mm off the base: the post's join no longer touches, so the body splits (the C1 limit).
    v = variant(top_off='plane_off - 5 mm')
    doc, des, r = first(S, v)
    before = H.snapshot(des)
    seen = {}
    for name, expr in halves_and_doubles(des, ['base_w', 'base_h']) + [('hole_n', '3'), ('plane_off', 'base_h + 6 mm')]:
        bad = trial(des, name, expr)
        diff = H.compare(before, H.snapshot(des))
        seen['%s = %s' % (name, expr)] = {'during': bad or 'ok', 'after': diff or 'same'}
        S.expect(not diff, 'after %s = %s and back: %s' % (name, expr, diff))
        if diff:
            break  # a lost reference stays lost, so later trials only repeat it
    S.info['trials'] = seen


def trials_hold(S, des, rows, tag, known=False):
    # known=True: a limit of Fusion's, flagged for the report rather than failed.
    before = H.snapshot(des)
    seen = {}
    for name, expr in rows:
        bad = trial(des, name, expr)
        seen['%s = %s' % (name, expr)] = bad or 'ok'
        if bad and known:
            S.flag('%s: %s = %s: %s' % (tag, name, expr, bad))
        else:
            S.expect(not bad, '%s: %s = %s: %s' % (tag, name, expr, bad))
    diff = H.compare(before, H.snapshot(des))
    S.expect(not diff, '%s: back as it was: %s' % (tag, diff))
    S.info.setdefault('trials', {})[tag] = seen


def fillet_edges(des, key):
    opened = open_groups(des.timeline)  # a step in a collapsed group can't be rolled to
    it = keyed(des, key)
    f = adsk.fusion.FilletFeature.cast(it.entity)
    with slow(note, 'marker before %s' % it.name):
        it.rollTo(True)  # a feature's edges can only be read with the marker just before it
    try:
        return sum(adsk.fusion.ConstantRadiusFilletEdgeSet.cast(f.edgeSets.item(i)).edges.count for i in range(f.edgeSets.count))
    finally:
        with slow(note, 'marker to the end'):
            des.timeline.moveToEnd()
        close_groups(opened)


@scenario
def l3(S):
    # The hole count changes, in the Parameters dialog and through the script, and the fillets after
    # the pattern keep their edges. Three shapes of it:
    rows = (('hole_n', '2'), ('hole_n', '3'), ('base_w', '60 mm'))

    # 1. The rounds and the chamfer after the pattern, on edges the holes don't touch.
    doc, des, r = first(S)
    trials_hold(S, des, rows, 'plain')
    v2 = set_param(variant(), 'hole_n', '3')
    r2 = S.run(doc, des, v2, 'three holes')
    S.need(r2)
    S.standard(doc, des, v2, r2)

    # 2. The holes sit on the back edge and cut it into pieces, and the chamfer on that edge comes
    # after them, so a count change makes new pieces. Hence fusion/rules.md rule 30: edge features
    # before the cuts that change.
    order = [k for k in M.ORDER if k != 'chamfer']
    after = variant(hole_y='base_d', alt={'chamfer': 'edges'})
    before = variant(hole_y='base_d', alt={'chamfer': 'edges'}, order=order[:order.index('hole_sketch')] + ['chamfer'] + order[order.index('hole_sketch'):],
                     uses={'chamfer': ('base',)})
    for tag, v in (('back edge, chamfer after the cuts', after), ('back edge, chamfer before the cuts', before)):
        doc, des = S.tab()
        r = S.run(doc, des, v, tag)
        S.need(r)
        trials_hold(S, des, rows, tag)

    # 3. Rounds on the holes' own top edges. After the pattern, a hole that goes takes its edge with
    # it, and Fusion keeps a cached copy with a warning. No library can keep an edge that is gone, so
    # that shape is a known limit, flagged, not failed. Patterned together with the
    # cut, the rounds come and go with their holes, and that shape must hold.
    order = list(M.ORDER)
    order.insert(order.index('hole_pattern') + 1, 'hole_rounds')
    v = variant(order=order)
    doc, des = S.tab()
    S.need(S.run(doc, des, v, 'rounds after the pattern'))
    trials_hold(S, des, rows[:2], 'rounds after the pattern', known=True)
    order = list(M.ORDER)
    order.insert(order.index('hole_pattern'), 'hole_rounds')
    v = variant(order=order, alt={'hole_pattern': 'with_rounds'}, uses={'hole_pattern': ('hole_cut', 'hole_rounds'), 'hole_rounds': ('hole_cut',)})
    doc, des = S.tab()
    S.need(S.run(doc, des, v, 'rounds in the pattern'))
    trials_hold(S, des, rows, 'rounds in the pattern')
    v2 = set_param(dict(v, params=[dict(p) for p in v['params']]), 'hole_n', '3')
    r2 = S.run(doc, des, v2, 'rounds in the pattern, three holes')
    S.need(r2)
    n = fillet_edges(des, 'hole_rounds')
    S.expect(n == 1, 'the rounds in the pattern have 1 edge, not %d' % n)
    S.standard(doc, des, v2, r2)


@scenario
def l4(S):
    # The library's parameter test, Builder.trials(), on a model with no ranges: every plain-value
    # parameter a step down and a step up, each put back. The test model has 7 plain values (14 trials;
    # the steps stage repeats them, so it makes none); post_h, pitch and plane_off are formulas, so they
    # are left alone. Then only=, values= and a name the design doesn't have.
    doc, des, r = first(S)
    before = H.snapshot(des)
    log = cad_apprentice.LiveLog(os.path.join(S.dir, 'trials.log'))
    try:
        b = cad_apprentice.Builder(des, doc, log)
        S.expect(b.trials(), 'the design came back after every trial: %s' % [l for l in log if 'DID NOT' in l])
        tried = [l for l in log if l.startswith('trial ')]
        S.expect(len(tried) == 14, '14 trials: %s' % tried)
        S.expect(not any(n in l for l in tried for n in ('post_h', 'pitch', 'plane_off')), 'no formula tried: %s' % tried)
        S.info['failed'] = b.trials_failed
        n = len(log)
        S.expect(b.trials(only=['wall'], values=[('hole_n', '6')]), 'only wall came back')
        again = [l for l in log[n:] if l.startswith('trial ')]
        S.expect(len(again) == 2 and all(l.startswith('trial wall = ') for l in again), 'only wall, twice: %s' % again)
        seen, start = [], b.size()
        b.trials(only=['base_w'], more=lambda d: seen.append(b.size()) or [])
        S.expect(len(seen) == 2 and all(x[0] != start[0] for x in seen), 'a trial changes the design: %s, was %s' % (seen, start))
        try:
            b.trials(only=['no_such'])
            S.fail('a name the design does not have was not refused')
        except Exception as err:
            S.expect('no_such' in str(err), 'the error names it: %s' % err)
    finally:
        log.close()
    diff = H.compare(before, H.snapshot(des))
    S.expect(not diff, 'the design is as it was: %s' % diff[:4])
    S.expect(not H.health(H.snapshot(des)), 'healthy: %s' % H.health(H.snapshot(des)))


@scenario
def l5(S):
    # Parameter ranges and the test's stages. param(range=, step=) saves the ranges in the design. ends:
    # hole_n at 2 and 6; round_r at 0.5 and 20 mm, where a 20 mm round on a 10 mm base fails, so the
    # test halves the gap to find the largest round that works and stops before the next stages. Then
    # steps, extremes and random sets on their own. A range on a formula is refused, and a later
    # Builder reads the ranges back from the design.
    doc, des, r = first(S)
    log = cad_apprentice.LiveLog(os.path.join(S.dir, 'trials.log'))
    tried = lambda n, start: [l.split(':')[0] for l in log[n:] if l.startswith('trial ' + start)]
    try:
        b = cad_apprentice.Builder(des, doc, log)
        b.param('hole_n', '4', '', 'Number of holes', False, range=(2, 6))
        b.param('round_r', '1 mm', 'mm', 'Round radius', False, range=('0.5 mm', '20 mm'), step='0.5 mm')
        try:
            b.param('pitch', 'base_w / 4', 'mm', 'Hole spacing', False, range=(5, 20), step=1)
            S.fail('a range on a formula was not refused')
        except Exception as err:
            S.expect('plain value' in str(err), 'the error says why: %s' % err)
        stored = [a.name for a in des.attributes.itemsByGroup('fusion_upsert') if a.name.startswith('range.')]
        S.expect(sorted(stored) == ['range.hole_n', 'range.round_r'], 'both ranges saved in the design: %s' % stored)
        before = H.snapshot(des)
        came_back = lambda ok: S.expect(ok, 'the design came back after every trial: %s' % [l for l in log if 'DID NOT' in l])

        n = len(log)
        came_back(b.trials(only=['hole_n', 'round_r']))
        S.expect(tried(n, 'hole_n') == ['trial hole_n = 2', 'trial hole_n = 6'], 'ends: hole_n at both ends: %s' % tried(n, 'hole_n'))
        rounds = tried(n, 'round_r')
        S.expect(rounds[:2] == ['trial round_r = 0.5 mm', 'trial round_r = 20 mm'] and len(rounds) > 2, 'ends: round_r at both ends, then the search: %s' % rounds)
        S.expect(any(l.startswith('RANGE TOO WIDE: round_r') for l in log[n:]), 'round_r reported as too wide')
        S.info['held'] = b.trials_held
        S.expect(b.trials_held.get('round_r', ('', ''))[1] not in ('', '20 mm'), 'the largest round that works is below 20 mm: %s' % b.trials_held)
        S.expect(any(l.startswith('the ends stage failed, so steps, extremes did not run') for l in log[n:]), 'stopped after the failed stage')

        n = len(log)
        came_back(b.trials(only=['hole_n', 'round_r'], tests=('steps',)))
        S.expect(tried(n, '') == ['trial hole_n = 3', 'trial hole_n = 5', 'trial round_r = 0.5 mm', 'trial round_r = 1.5 mm'],
                 'steps: one step either side: %s' % tried(n, ''))

        n = len(log)
        came_back(b.trials(only=['hole_n', 'round_r'], tests=('extremes',)))
        ext = [l for l in log[n:] if l.startswith('trial all ')]
        S.expect(len(ext) == 3 and ext[0] == 'trial all low: ok' and ext[1].startswith('trial all high: FAILED')
                 and ext[2].startswith('trial all low, then all high: FAILED'),
                 'extremes: all low, all high, then all high from all low, the last two failing on the round: %s' % ext)
        S.expect(any(l.startswith('  the set: hole_n = 6, round_r = 20 mm') for l in log[n:]), 'the failed set is logged')

        n = len(log)
        came_back(b.trials(only=['hole_n', 'round_r'], tests=('random',), runs=3, seed=1))
        S.expect(tried(n, 'random') == ['trial random %d of 3' % k for k in (1, 2, 3)], 'random: 3 sets: %s' % tried(n, 'random'))
        S.expect(any(l == 'random sets: 3, seed 1' for l in log[n:]), 'the seed is logged')

        n = len(log)
        b2 = cad_apprentice.Builder(des, doc, log)
        came_back(b2.trials(only=['hole_n'], tests=('ends',)))
        S.expect(len(tried(n, 'hole_n')) == 2, 'a later Builder reads the range back from the design: %s' % tried(n, 'hole_n'))
    finally:
        log.close()
    diff = H.compare(before, H.snapshot(des))
    S.expect(not diff, 'the design is as it was: %s' % diff[:4])


@scenario
def l6(S):
    # Builder.back_to_saved(), the last call after the parameter test. A trial puts its value back, but
    # Fusion still counts the tab as changed. It closes the tab without saving and opens the saved
    # version: one tab of the design, the same version, the design as it was, and nothing unsaved.
    doc, des, fid, r = saved_first(S)
    n = H.latest_version(fid)
    before = H.snapshot(des)
    log = cad_apprentice.LiveLog(os.path.join(S.dir, 'back.log'))
    try:
        b = cad_apprentice.Builder(des, doc, log)
        was = des.userParameters.itemByName('base_w').expression
        hand_param(des, 'base_w', '45 mm')
        hand_param(des, 'base_w', was)
        S.expect(doc.isModified, 'the trial marks the tab as changed')
        b.back_to_saved()
    finally:
        log.close()
    S.expect(any('went back to the last saved version, %d' % n in l for l in log), 'went back to version %d: %s' % (n, log[-3:]))
    S.expect(not doc.isValid, 'the changed tab is closed')
    S.expect(H.latest_version(fid) == n, 'nothing saved: %d, was %d' % (H.latest_version(fid), n))
    doc, des = H.reopened(S, fid)
    if not S.expect(des is not None, 'the saved version is open'):
        return
    tabs = [d for d in H.app.documents if d.isValid and H.file_of(d) and H.file_of(d).id == fid]
    S.expect(len(tabs) == 1, 'one tab of the design: %d' % len(tabs))
    S.expect(not doc.isModified, 'the tab has nothing unsaved')
    diff = H.compare(before, H.snapshot(des))
    S.expect(not diff, 'the design is as it was: %s' % diff[:4])


# M. Logging

@scenario
def m1(S):
    doc, des, r = first(S)
    path = os.path.join(S.dir, '01-v1.log')
    lines = open(path).read().splitlines()
    untimed = [l for l in lines if not re.match(r'\d\d:\d\d:\d\d ', l)]
    S.expect(lines and not untimed, 'every line has a time: %s' % untimed[:3])
    missing = [l for l in r['log'] if not any(x.endswith(' ' + l) for x in lines)]
    S.expect(not missing, 'every log line is in the file: %s' % missing[:3])
    log = cad_apprentice.LiveLog(os.path.join(S.dir, 'live.log'))
    log.append('first line')
    S.expect('first line' in open(os.path.join(S.dir, 'live.log')).read(), 'written before the log is closed')
    log.close()


@scenario
def m2(S):
    # A step raises: the last progress line before STOPPED names it.
    doc, des, r = first(S)
    r2 = S.run(doc, des, variant(order=M.ORDER + ['boom']), 'boom')
    S.expect(not r2['ok'] and 'boom, on purpose' in (r2['error'] or ''), 'it stops: %s' % r2['error'])
    lines = open(os.path.join(S.dir, '02-boom.log')).read().splitlines()
    steps = [l for l in lines if '  step ' in l]
    S.expect(steps and steps[-1].endswith('step Boom'), 'the last step line names it: %s' % steps[-1:])
    S.expect(any('STOPPED' in l and 'Boom' in l for l in lines), 'STOPPED names it: %s' % [l for l in lines if 'STOPPED' in l])
    S.info['tail'] = lines[-4:]


# Saved design: A5, A6, D3, F4, K. Each opens the one saved test design, clears it and builds there.

def saved_first(S, v=None, label='v1'):
    doc, des, fid = H.saved_tab(S)
    n = H.latest_version(fid)
    r = S.run(doc, des, v or variant(), label, save_note='cad_apprentice test %s: %s' % (S.sid, label))
    S.need(r)
    S.expect(H.wait_version(fid, n + 1, log=S.note), 'version 1 reached the cloud')
    return doc, des, fid, r


def saves(r):
    return [l for l in r['log'] if l.startswith('saved:')]


def his_post_round(des):
    # A round put by hand on the post's four upright edges, in the component the post is in.
    body = keyed(des, 'base').entity.bodies.item(0)
    top = des.userParameters.itemByName('base_h').value
    c = adsk.core.ObjectCollection.create()
    for e in body.edges:
        bb = e.boundingBox
        if bb.minPoint.z > top - M.EPS and bb.maxPoint.z - bb.minPoint.z > M.EPS and abs(bb.maxPoint.x - bb.minPoint.x) < M.EPS and abs(bb.maxPoint.y - bb.minPoint.y) < M.EPS:
            c.add(e)
    ff = body.parentComponent.features.filletFeatures
    fi = ff.createInput()
    fi.edgeSetInputs.addConstantRadiusEdgeSet(c, vi('0.5 mm'), False)
    with slow(note, 'hand edit: round on the post'):
        f = ff.add(fi)
    f.name = 'Hand post round'
    return f, c.count


def his_plane_on_top(des):
    tp = keyed(des, 'top_plane').entity
    comp = tp.component
    pi = comp.constructionPlanes.createInput()
    pi.setByOffset(tp, vi('2 mm'))
    with slow(note, 'hand edit: plane on top'):
        p = comp.constructionPlanes.add(pi)
    p.name = 'Hand top plane'
    return p


def went_back(S, r, fid, want_version, before, tag):
    # The run says BROKEN or STOPPED and went back: the open tab is the saved version, as it was.
    S.expect(any('went back to the last saved version, %d' % want_version in l for l in r['log']),
             '%s: went back to version %d: %s' % (tag, want_version, [l for l in r['log'] if 'went back' in l or 'never saved' in l]))
    S.expect(H.latest_version(fid) == want_version, '%s: nothing else saved, latest %d' % (tag, H.latest_version(fid)))
    doc, des = H.reopened(S, fid)
    S.expect(des is not None, '%s: the saved version is open' % tag)
    if des is not None:
        diff = H.compare(before, H.snapshot(des))
        S.expect(not diff, '%s: it is the design as it was: %s' % (tag, diff))
        S.expect(not H.health(H.snapshot(des)), '%s: healthy: %s' % (tag, H.health(H.snapshot(des))))
    return doc, des


@scenario
def a6(S):
    v = variant()
    doc, des, fid, r = saved_first(S, v)
    keys = sorted(filter(None, (_attr(it.entity, 'key') for it in timeline_items(des.timeline))))
    n = H.latest_version(fid)
    with slow(note, 'close the tab, then open the saved design again'):
        doc.close(False)
        doc = H.app.documents.open(H.app.data.findFileById(fid))
    des = H.design_of(doc)
    S.tabs.append(doc)
    again = sorted(filter(None, (_attr(it.entity, 'key') for it in timeline_items(des.timeline))))
    S.expect(again == keys, 'the keys came back: %d of %d' % (len(again), len(keys)))
    r2 = S.run(doc, des, v, 'reopened', save_note='cad_apprentice test A6: rerun')
    S.need(r2)
    S.expect(not changed_steps(r2) and not r2['params_set'], 'nothing reruns: %s %s' % (changed_steps(r2), r2['params_set']))
    S.expect(not saves(r2) and H.latest_version(fid) == n, 'nothing saved: %s' % saves(r2))
    S.standard(doc, des, v, r2, rerun=False)


@scenario
def d3(S):
    doc, des, fid, r = saved_first(S)
    f, n_edges = his_post_round(des)
    S.info['hand edges'] = n_edges
    n = H.latest_version(fid)
    with slow(note, 'save the hand round'):
        doc.save('hand round')
    S.expect(H.wait_version(fid, n + 1, log=S.note), 'the hand round reached the cloud')
    before = H.snapshot(des)
    v2 = variant(post_draw=lambda w, d: M.circle('(%s) / 2' % w, '(%s) / 2' % w, w))
    r2 = S.run(doc, des, v2, 'post redrawn round', save_note='cad_apprentice test D3: v2')
    # The spec first said BROKEN. The library now stops before it deletes a step the hand round hangs on,
    # so a STOPPED that names the hand round is the safer outcome and passes too.
    S.expect(not r2['ok'] and (logged(r2, 'BROKEN') or logged(r2, 'STOPPED')) and logged(r2, 'Hand post round'),
             'BROKEN or STOPPED names the hand round: %s' % [l for l in r2['log'] if 'BROKEN' in l or 'STOPPED' in l])
    went_back(S, r2, fid, n + 1, before, 'D3')


@scenario
def f4(S):
    doc, des, fid, r = saved_first(S)
    his_plane_on_top(des)
    n = H.latest_version(fid)
    with slow(note, 'save the hand plane'):
        doc.save('hand plane')
    S.expect(H.wait_version(fid, n + 1, log=S.note), 'the hand plane reached the cloud')
    before = H.snapshot(des)
    # The post sketch moves to the XY plane, so it no longer uses the top plane. The script must say so
    # (as in E5): with the old uses, the library sees no change and leaves the sketch on the deleted plane.
    v2 = variant(order=[k for k in M.ORDER if k not in ('top_plane', 'mark_sketch')], alt={'post_sketch': 'on_xy'}, uses={'post_sketch': ()})
    r2 = S.run(doc, des, v2, 'top plane removed', save_note='cad_apprentice test F4: v2')
    S.info['log'] = short_log(r2)
    S.expect(not r2['ok'] and (logged(r2, 'BROKEN') or logged(r2, 'STOPPED')), 'BROKEN or a clear stop: %s' % [l for l in r2['log'] if 'BROKEN' in l or 'STOPPED' in l])
    went_back(S, r2, fid, n + 1, before, 'F4')


@scenario
def k1(S):
    v = variant()
    doc, des, fid, r = saved_first(S, v)
    n = H.latest_version(fid)
    S.info['modified after the save'] = doc.isModified
    r2 = S.run(doc, des, v, 'no change', save_note='cad_apprentice test K1: rerun')
    S.need(r2)
    S.expect(not saves(r2) and not logged(r2, 'restore point'), 'nothing saved: %s' % [l for l in r2['log'] if 'save' in l or 'restore' in l])
    S.expect(H.latest_version(fid) == n, 'still version %d, not %d' % (n, H.latest_version(fid)))


@scenario
def k2(S):
    doc, des, fid, r = saved_first(S)
    n = H.latest_version(fid)
    v2 = set_param(variant(), 'base_w', '45 mm')
    note = 'cad_apprentice test K2: base_w 45 mm'
    r2 = S.run(doc, des, v2, 'base_w', save_note=note)
    S.need(r2)
    S.expect(len(saves(r2)) == 1 and not logged(r2, 'restore point'), 'saved once: %s' % saves(r2))
    S.expect(H.wait_version(fid, n + 1, log=S.note) and H.latest_version(fid) == n + 1, 'one new version: %d, was %d' % (H.latest_version(fid), n))
    try:
        S.info['note'] = H.app.data.findFileById(fid).latestVersion.description
        S.expect(S.info['note'] == note, 'the version has the note: %s' % S.info['note'])
    except Exception as err:
        S.flag('could not read the version note: %s' % err)


@scenario
def k3(S):
    # An unsaved hand change at the start: a restore point first, then the run's own save.
    doc, des, fid, r = saved_first(S)
    n = H.latest_version(fid)
    hand_param(des, 'base_d', '35 mm')
    S.expect(doc.isModified, 'the hand change marks the tab')
    v2 = set_param(variant(), 'base_w', '45 mm')
    r2 = S.run(doc, des, v2, 'base_w', save_note='cad_apprentice test K3: v2')
    S.need(r2)
    S.expect(logged(r2, 'restore point saved'), 'a restore point: %s' % short_log(r2)[:6])
    S.expect(len(saves(r2)) == 1, 'then one save: %s' % saves(r2))
    S.expect(H.wait_version(fid, n + 2, log=S.note) and H.latest_version(fid) == n + 2, 'two new versions: %d, was %d' % (H.latest_version(fid), n))
    S.expect(des.userParameters.itemByName('base_d').expression == '35 mm', 'the hand value stays')


@scenario
def k4(S):
    # K4 and K5 (K5 has no function of its own): an unsaved hand round, then a run that breaks it. The restore point holds the hand round,
    # and the go-back must open the restore point, not the version before it.
    doc, des, fid, r = saved_first(S)
    n = H.latest_version(fid)
    his_post_round(des)
    before = H.snapshot(des)
    v2 = variant(post_draw=lambda w, d: M.circle('(%s) / 2' % w, '(%s) / 2' % w, w))
    r2 = S.run(doc, des, v2, 'post redrawn round', save_note='cad_apprentice test K4: v2')
    S.expect(logged(r2, 'restore point saved'), 'a restore point first')
    # BROKEN or STOPPED: both go back the same way, and the library now stops before it breaks the hand round (see D3).
    S.expect(not r2['ok'] and (logged(r2, 'BROKEN') or logged(r2, 'STOPPED')), 'BROKEN or STOPPED: %s' % [l for l in r2['log'] if 'BROKEN' in l or 'STOPPED' in l])
    S.info['waited'] = [l for l in r2['log'] if 'not shown up' in l]
    went_back(S, r2, fid, n + 1, before, 'K4')


@scenario
def k6(S):
    doc, des, fid, r = saved_first(S)
    n = H.latest_version(fid)
    before = H.snapshot(des)
    v2 = set_param(variant(die_at='post'), 'base_w', '45 mm')
    r2 = S.run(doc, des, v2, 'dies at post', save_note='cad_apprentice test K6: v2')
    S.expect(not r2['ok'] and logged(r2, 'STOPPED'), 'STOPPED: %s' % [l for l in r2['log'] if 'STOPPED' in l])
    went_back(S, r2, fid, n, before, 'K6')


@scenario
def k7(S):
    # Known limit, measured, never a failure: does a no-change rerun mark the tab as changed?
    v = variant()
    doc, des, fid, r = saved_first(S, v)
    S.info['modified after the first save'] = doc.isModified
    r2 = S.run(doc, des, v, 'no change')
    S.need(r2)
    S.info['modified after a no-change rerun'] = doc.isModified
    if doc.isModified:
        S.flag('a no-change rerun marks the tab as changed (K7 known limit)')


@scenario
def k8(S):
    # Decision 1: the go-back itself fails. Fusion's close is made to refuse, so the tab stays half-built.
    # The run says COULD NOT GO BACK and keeps its own error. The next run in that tab saves no restore
    # point of the half-built design: if it fails, it goes back to the last good version, and if it
    # works, the mark is cleared.
    doc, des, fid, r = saved_first(S)
    n = H.latest_version(fid)
    before = H.snapshot(des)

    def refused_close(doc, des, label):
        real = cad_apprentice._close

        def refuse(doc):
            raise RuntimeError('close refused on purpose (K8)')
        cad_apprentice._close = refuse
        try:
            r = S.run(doc, des, set_param(variant(die_at='post'), 'base_w', '45 mm'), label, save_note='cad_apprentice test K8: %s' % label)
        finally:
            cad_apprentice._close = real
        S.expect(not r['ok'] and 'stopped on purpose after post' in (r['error'] or ''), '%s: its own error is kept: %s' % (label, r['error']))
        S.expect(not r.get('abort_error'), '%s: abort did not raise: %s' % (label, (r.get('abort_error') or '')[-300:]))
        S.expect(logged(r, 'COULD NOT GO BACK'), '%s: says so: %s' % (label, short_log(r)[-4:]))
        return S.expect(doc.isValid, '%s: the half-built tab is still open' % label)

    if not refused_close(doc, des, 'go-back refused'):
        H.reopened(S, fid)  # It went back after all: the tab it opened is closed at the end, and the rest can't run.
        return
    S.expect(H.latest_version(fid) == n, 'nothing saved: %d, was %d' % (H.latest_version(fid), n))
    S.expect(_attr(des, 'go_back_to') == str(n), 'the tab remembers version %d: %s' % (n, _attr(des, 'go_back_to')))
    # The next run fails too: no restore point of the half-built tab, and back to version n.
    r3 = S.run(doc, des, variant(die_at='post'), 'dies again', save_note='cad_apprentice test K8: dies again')
    S.expect(not logged(r3, 'restore point saved'), 'no restore point of the half-built tab: %s' % short_log(r3)[:4])
    doc, des = went_back(S, r3, fid, n, before, 'K8 next run fails')
    if des is None:
        return
    # Half-built again, then a run that works: it saves, and the mark is gone.
    if not refused_close(doc, des, 'go-back refused again'):
        H.reopened(S, fid)
        return
    v2 = set_param(variant(), 'base_w', '45 mm')
    r5 = S.run(doc, des, v2, 'works', save_note='cad_apprentice test K8: works')
    S.need(r5)
    S.expect(not logged(r5, 'restore point saved'), 'no restore point of the half-built tab: %s' % short_log(r5)[:4])
    S.expect(_attr(des, 'go_back_to') is None, 'the mark is cleared: %s' % _attr(des, 'go_back_to'))
    S.expect(H.wait_version(fid, n + 1, log=S.note) and H.latest_version(fid) == n + 1, 'saved once: %d, was %d' % (H.latest_version(fid), n))
    S.standard(doc, des, v2, r5, rerun=False)


@scenario
def k9(S):
    # F2: an unsaved hand edit, then a run that stops before its first change. The hand edit must
    # survive: a restore point first, and the go-back opens it.
    doc, des, fid, r = saved_first(S)
    n = H.latest_version(fid)
    hand_param(des, 'base_d', '35 mm')
    before = H.snapshot(des)
    r2 = S.run(doc, des, variant(die_at='base_sketch'), 'dies before a change', save_note='cad_apprentice test K9: v2')
    S.expect(not r2['ok'] and logged(r2, 'STOPPED'), 'STOPPED: %s' % r2['error'])
    S.expect(logged(r2, 'restore point saved'), 'a restore point first: %s' % short_log(r2)[:4])
    doc, des = went_back(S, r2, fid, n + 1, before, 'K9')
    if des is not None:
        got = des.userParameters.itemByName('base_d').expression
        S.expect(got == '35 mm', 'the hand value survives: %s' % got)


@scenario
def k10(S):
    # F3: a clean run wipes the design, then fails. The go-back must open the version from before the
    # wipe, and nothing is saved: not the empty design, not a restore point.
    doc, des, fid, r = saved_first(S)
    n = H.latest_version(fid)
    before = H.snapshot(des)
    from cad_apprentice.helpers import wipe
    wiped = []
    was = wipe(doc, des, wiped)
    S.info['wipe'] = wiped
    S.expect(was == n, 'wipe says version %s, the latest is %d' % (was, n))
    r2 = S.run(doc, des, variant(die_at='post'), 'clean run dies', save_note='cad_apprentice test K10: v2', go_back_to=was)
    S.expect(not r2['ok'] and logged(r2, 'STOPPED'), 'STOPPED: %s' % r2['error'])
    S.expect(not logged(r2, 'restore point saved'), 'no restore point of the wiped design: %s' % short_log(r2)[:4])
    went_back(S, r2, fid, n, before, 'K10')
