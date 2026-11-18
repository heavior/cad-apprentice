# Joints between parts, built by the library. Five boxes, each in its own component, held
# by three joints and an as-built joint. Run 1 builds them. Then a hand-made part and joint go in after
# them, so a replace of any joint would be refused. Run 2 changes every joint's values, sides or motion,
# which must edit each one in place. Run 3 changes nothing. Run through the UpsertTestRunner add-in:
# {"id": "joints", "file": "tests/test_joints.py", "args": {}}
import os
import adsk.core, adsk.fusion
import upsert_harness as H
from cad_apprentice import vi
from test_features import rect, health, same_value

New = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
P = adsk.core.Point3D.create
JOINTS = ('j_arm', 'j_wheel', 'j_slide', 'ab_lid')
NAMES = {'j_arm': 'Arm on base', 'j_wheel': 'Wheel on arm', 'j_slide': 'Slide on base', 'ab_lid': 'Lid on base'}
# What each joint's value reader should say, and where the arm sits, per version.
WANT = {'v1': (dict(j_arm='rigid;0.5 cm;0 deg;False', j_wheel='revolute z;0 cm;30 deg;False',
                    j_slide='slider z;0 cm;0 deg;False', ab_lid='rigid'), (0, 0, 1.5)),
        'v2': (dict(j_arm='rigid;1 cm;0 deg;False', j_wheel='revolute z;0 cm;45 deg;False',
                    j_slide='revolute x;0 cm;0 deg;True', ab_lid='revolute z'), (4, 0, 2))}
WANT['v3'] = WANT['v2']


def box(b, key, name, w, d, h):
    with b.component(key, name) as comp:
        sk = b.sketch(key + '_sk', name + ' sketch', lambda: comp.xYConstructionPlane, rect((0, 0, 0), (w, d, 0)))
        b.extrude(key + '_box', name + ' box', sk, New, distance='%s cm' % h, body_name=name)


def corner(b, key, x, y, z):
    # The box's corner nearest (x, y, z), in its own component. The library sees it from the top.
    return lambda: min(b.body(key + '_box').vertices, key=lambda p: p.geometry.distanceTo(P(x, y, z)))


def describe(b, v):
    box(b, 'base', 'Base', 4, 4, 1)
    box(b, 'arm', 'Arm', 1, 3, 0.5)
    box(b, 'wheel', 'Wheel', 1, 1, 0.3)
    box(b, 'slide', 'Slide', 1, 1, 0.5)
    box(b, 'lid', 'Lid', 2, 2, 0.2)
    on_base = v['arm_on']
    b.joint('j_arm', 'Arm on base', corner(b, 'arm', 0, 0, 0), corner(b, 'base', *on_base), offset=v['arm_off'],
            uses=['arm_box', 'base_box'])
    b.joint('j_wheel', 'Wheel on arm', corner(b, 'wheel', 0, 0, 0), corner(b, 'arm', 0, 3, 0.5), motion='revolute',
            angle=v['wheel_angle'], uses=['wheel_box', 'arm_box'])
    slide_motion, slide_axis, slide_flip = v['slide']
    b.joint('j_slide', 'Slide on base', corner(b, 'slide', 0, 0, 0), corner(b, 'base', 4, 4, 1), motion=slide_motion,
            axis=slide_axis, flip=slide_flip, uses=['slide_box', 'base_box'])
    lid_motion = v['lid']
    b.as_built_joint('ab_lid', 'Lid on base', lambda: b.known['lid'], lambda: b.known['base'], motion=lid_motion,
                     at=corner(b, 'lid', 0, 0, 0) if lid_motion != 'rigid' else None, uses=['lid', 'base', 'lid_box'])


def hand_joint(des):
    # A part and a joint, made by hand as a person would: no fusion_upsert attributes, after the script's joints.
    root = des.rootComponent
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())  # slow-ok: test setup
    occ.component.name = 'Hand pin'
    sk = occ.component.sketches.add(occ.component.xYConstructionPlane)  # slow-ok: test setup, one small sketch
    sk.sketchCurves.sketchLines.addTwoPointRectangle(P(0, 0, 0), P(0.5, 0.5, 0))
    ei = occ.component.features.extrudeFeatures.createInput(sk.profiles.item(0), New)
    ei.setDistanceExtent(False, vi('2 cm'))
    occ.component.features.extrudeFeatures.add(ei)  # slow-ok: test setup, one small extrude
    base = root.occurrences.itemByName('Base:1')
    ai = root.asBuiltJoints.createInput(occ, base, None)
    ai.setAsRigidJointMotion()
    j = root.asBuiltJoints.add(ai)  # slow-ok: test setup, one joint
    j.name = 'Hand joint'
    return j


def values(b):
    out = {}
    for k in JOINTS:
        j = b.known.get(k)
        if j is None or not j.isValid or k not in b.made:
            out[k] = 'not built'
            continue
        out[k] = b.made[k][6](j)
    return out


def main(args):
    versions = (('v1', dict(arm_on=(0, 0, 1), arm_off='0.5 cm', wheel_angle='30 deg', slide=('slider', 'z', False), lid='rigid')),
                ('v2', dict(arm_on=(4, 0, 1), arm_off='1 cm', wheel_angle='45 deg', slide=('revolute', 'x', True), lid='revolute')),
                ('v3', dict(arm_on=(4, 0, 1), arm_off='1 cm', wheel_angle='45 deg', slide=('revolute', 'x', True), lid='revolute')))
    out = {}
    V = H.Verdict()
    doc, des = H.new_tab()
    um = des.unitsManager
    try:
        tokens = hand = None
        for label, v in versions:
            r = H.build(doc, des, describe, v, os.path.join(OUT_DIR, 'joints-%s.log' % label))
            b = r.get('builder')
            now = {k: b.known[k].entityToken for k in JOINTS if b and k in b.known and b.known[k].isValid}
            out[label] = {'ok': r['ok'], 'error': r.get('trace') or r['error'], 'counts': r.get('counts'),
                          'touched': r.get('touched'), 'health': health(des),
                          'log': r['log'][-12:] if r['error'] else [l for l in r['log'] if 'could not' in l or 'BROKEN' in l or 'top component' in l],
                          'values': values(b) if b else None,
                          'arm_at': [round(x, 3) for x in b.known['arm'].transform2.translation.asArray()] if b and 'arm' in b.known else None,
                          'same_joints': tokens is None or now == tokens,
                          'hand_ok': hand is None or (hand.isValid and hand.timelineObject.healthState == adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState)}
            # v2 changes every joint, so all four must be edited in place; v3 changes nothing.
            want = {NAMES[k]: 'updated' for k in JOINTS} if label == 'v2' else None
            if not V.run(label, r, des, first=label == 'v1', want=want):
                break
            o = out[label]
            V.expect(o['same_joints'], '%s: a joint was replaced, not edited in place' % label)
            V.expect(o['hand_ok'], '%s: the hand-made joint broke' % label)
            values_want, arm_want = WANT[label]
            for k in JOINTS:
                V.expect(same_value(um, o['values'][k], values_want[k]),
                         '%s: %s reads %s, not %s' % (label, NAMES[k], o['values'][k], values_want[k]))
            V.expect(o['arm_at'] and all(abs(a - w) < 1e-3 for a, w in zip(o['arm_at'], arm_want)),
                     '%s: the arm sits at %s, not %s' % (label, o['arm_at'], list(arm_want)))
            if tokens is None:
                tokens = now
                hand = hand_joint(des)
        out['joints in design'] = [j.name for j in des.rootComponent.joints] + [j.name for j in des.rootComponent.asBuiltJoints]
    finally:
        H.close_tab(doc)
    return V.result(**out)
