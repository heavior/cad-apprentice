# Two edits the library could only make by replacing the feature, tried in place. Each
# design gets a hand-made block after the step under test, so a replace would be refused: the step
# must keep its identity, end healthy, and leave the hand-made block working. Run through the
# UpsertTestRunner add-in:
# {"id": "in-place", "file": "tests/test_edit_in_place.py", "args": {}}
#   - fillet: a fillet with two edge sets, after its body is redrawn wider (G4).
#   - loft: a section's sketch redrawn as another shape, then the section moved to another sketch.
import os
import adsk.core, adsk.fusion
import upsert_harness as H
from cad_apprentice import vi
from test_features import rect, circle, top_face, health

New = adsk.fusion.FeatureOperations.NewBodyFeatureOperation


def top_edge(body, pick):
    # The top edge at the back (pick=max) or the front (pick=min) of a bar.
    c = adsk.core.ObjectCollection.create()
    c.add(pick(top_face(body).edges, key=lambda e: e.pointOnEdge.y))
    return c


def fillet_design(b, v):
    xy = b.comp.xYConstructionPlane
    sk = b.sketch('bar_sk', 'Bar sketch', lambda: xy, rect((0, 0, 0), (v['w'], 2, 0)))
    b.extrude('bar', 'Bar', sk, New, distance='1 cm', body_name='Bar')
    r1, r2 = v['r']
    b.fillet('rounds', 'Two-set fillet', lambda: [(top_edge(b.body('bar'), max), r1), (top_edge(b.body('bar'), min), r2)],
             uses=['bar'])


def loft_design(b, v):
    xy = b.comp.xYConstructionPlane
    low = b.sketch('low', 'Loft base', lambda: xy, circle(0, 0, 0, 1))
    b.offset_plane('high_pl', 'Loft high', xy, '3 cm')
    shape = {'circle': circle(0, 0, 3, 0.5), 'square': rect((-0.5, -0.5, 3), (0.5, 0.5, 3))}[v['shape']]
    b.sketch('high', 'Loft top', lambda: b.known['high_pl'], shape, uses=['high_pl'])
    b.sketch('high2', 'Loft top, wider', lambda: b.known['high_pl'], rect((-0.8, -0.8, 3), (0.8, 0.8, 3)), uses=['high_pl'])
    top = v['top']
    b.loft('loft', 'Loft', lambda: [low.profiles.item(0), b.known[top].profiles.item(0)], New, body_name='Loft', uses=['low', top])


def hand_block(des):
    # A separate block, made by hand as a person would: no fusion_upsert attributes. It sits after the step under test,
    # so replacing that step would be refused.
    comp = des.rootComponent
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.sketchCurves.sketchLines.addTwoPointRectangle(adsk.core.Point3D.create(10, 10, 0), adsk.core.Point3D.create(11, 11, 0))
    ei = comp.features.extrudeFeatures.createInput(sk.profiles.item(0), New)
    ei.setDistanceExtent(False, vi('1 cm'))
    f = comp.features.extrudeFeatures.add(ei)
    f.name = 'Hand block'
    return f


def run(V, describe, body_name, key, step_name, versions):
    # Each version after the first changes what the step under test uses, except the last, which
    # changes nothing. The step must be edited in place every time: same feature, nothing replaced,
    # no "could not edit" line, the hand-made block still healthy.
    out = {}
    doc, des = H.new_tab()
    try:
        token = hand = None
        disagree = []
        for n, (label, v) in enumerate(versions):
            r = H.build(doc, des, describe, v, os.path.join(OUT_DIR, '%s-%s.log' % (key, label)))
            ent = r['builder'].known.get(key) if r.get('builder') else None
            same = token is None or (ent is not None and ent.isValid and ent.entityToken == token)
            # Decision 3 (audit F48): Autodesk says two tokens for one feature can differ, and that
            # findEntityByToken is the way to compare. Check both ways and record where they disagree.
            found = token is None or (ent is not None and ent.isValid and any(x == ent for x in des.findEntityByToken(token)))
            if found != same:
                disagree.append('%s: the token strings say %s, findEntityByToken says %s' % (label, same, found))
            hand_ok = hand is None or hand.isValid and hand.healthState == adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState
            out[label] = {'ok': r['ok'], 'error': r.get('trace') or r['error'], 'counts': r.get('counts'),
                          'touched': r.get('touched'), 'health': health(des), 'log': r['log'][-12:] if r['error'] else
                          [l for l in r['log'] if 'could not edit' in l or 'BROKEN' in l],
                          'same_feature': same, 'found_by_token': found, 'hand_ok': hand_ok}
            tag = '%s %s' % (key, label)
            if not V.expect(not r['error'], '%s: the run failed: %s' % (tag, r['error'])):
                break
            for line in health(des):
                V.fails.append('%s: not healthy: %s' % (tag, line))
            c = r.get('counts') or {}
            if n == 0:
                V.expect(not any(c.get(k) for k in ('updated', 'replaced', 'same', 'removed')),
                         '%s: a first build should only create: %s' % (tag, c))
                token = ent.entityToken
                # A feature must find itself, or the == below proves nothing.
                V.expect(any(x == ent for x in des.findEntityByToken(token)), '%s: findEntityByToken does not find the feature' % tag)
                hand = hand_block(des)
                continue
            V.expect(not c.get('replaced'), '%s: %s steps were replaced, not edited in place' % (tag, c.get('replaced')))
            for line in r['log']:
                if line.startswith('could not edit '):
                    V.fails.append('%s: %s' % (tag, line))
            V.expect(same, '%s: %s is no longer the same feature' % (tag, step_name))
            V.expect(hand_ok, '%s: the hand-made block broke' % tag)
            touched = {name: what for what, name, why in r.get('touched', [])}
            if n < len(versions) - 1:
                V.expect(touched.get(step_name) == 'updated', '%s: %s should be updated, but was %s'
                         % (tag, step_name, touched.get(step_name, 'left as it was')))
            else:
                V.expect(not (c.get('updated') or c.get('replaced') or c.get('created')),
                         '%s: a rerun with nothing changed still changed steps: %s' % (tag, c))
        body = des.rootComponent.bRepBodies.itemByName(body_name)
        out['volume'] = round(body.volume, 5) if body else None
        out['token_disagree'] = disagree
    finally:
        H.close_tab(doc)
    return out


def main(args):
    V = H.Verdict()
    fillet = run(V, fillet_design, 'Bar', 'rounds', 'Two-set fillet', (('v1', dict(w=4, r=('1 mm', '2 mm'))),
                                                                       ('v2', dict(w=5, r=('1 mm', '2 mm'))),
                                                                       ('v3', dict(w=5, r=('1.5 mm', '2.5 mm'))),
                                                                       ('v4', dict(w=5, r=('1.5 mm', '2.5 mm')))))
    loft = run(V, loft_design, 'Loft', 'loft', 'Loft', (('v1', dict(shape='circle', top='high')),
                                                       ('v2', dict(shape='square', top='high')),
                                                       ('v3', dict(shape='square', top='high2')),
                                                       ('v4', dict(shape='square', top='high2'))))
    return V.result(fillet=fillet, loft=loft)
