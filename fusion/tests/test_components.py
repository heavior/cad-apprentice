# Proves steps can live in subcomponents, in one unsaved tab that it closes at the end: builds
# two parts and a nested one, then reruns with no change, a parameter change, a redrawn sketch,
# a step added and removed, a step the script moves, a dropped part, and a redraw that breaks a
# hand-made feature. No saved design is touched. Run it through the runner, or with ▶ from
# FusionUpsertTest.py.
import os, traceback
import adsk.core, adsk.fusion
import cad_apprentice

LOG = os.path.join(OUT_DIR, 'FusionUpsertTest.log')
PROGRESS = os.path.join(OUT_DIR, 'progress.log')  # every line as it comes, with each Fusion call of a second or more timed
NEW_BODY = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
MY_FILLET = 'My fillet, made by hand'


def point(x, y):
    return adsk.core.Point3D.create(x, y, 0)


def rectangle(width, depth):
    def draw(s):
        lines = s.sketchCurves.sketchLines.addTwoPointRectangle(point(0, 0), point(2, 2))
        gc = s.geometricConstraints
        gc.addCoincident(lines.item(0).startSketchPoint, s.originPoint)
        gc.addHorizontal(lines.item(0))
        gc.addVertical(lines.item(1))
        gc.addHorizontal(lines.item(2))
        gc.addVertical(lines.item(3))
        dims = s.sketchDimensions
        horizontal = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
        vertical = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation
        dims.addDistanceDimension(lines.item(0).startSketchPoint, lines.item(0).endSketchPoint, horizontal, point(1, -1)).parameter.expression = width
        dims.addDistanceDimension(lines.item(1).startSketchPoint, lines.item(1).endSketchPoint, vertical, point(3, 1)).parameter.expression = depth
    return draw


def top_edges(b, key):
    body = b.body(key)
    top = body.boundingBox.maxPoint.z
    c = adsk.core.ObjectCollection.create()
    for e in body.edges:
        if e.boundingBox.minPoint.z > top - 0.001:
            c.add(e)
    return c


def extra_plane(b):
    pi = b.comp.constructionPlanes.createInput()
    pi.setByOffset(b.comp.xYConstructionPlane, cad_apprentice.vi('5 mm'))
    return b.comp.constructionPlanes.add(pi)


def describe(b, a_version='1', with_c=True, extra=False, a_sketch_in_b=False, b_version='1'):
    b.param('width', '20 mm', 'mm')
    b.param('depth', '30 mm', 'mm')
    b.param('tall', '10 mm', 'mm')
    with b.group('Part A'):
        with b.component('part_a', 'Part A') as comp:
            if not a_sketch_in_b:
                s = b.sketch('a_sketch', 'A outline', lambda: comp.xYConstructionPlane, rectangle('width', 'depth'), spec=(a_version,))
                if extra:
                    b.plane('a_extra', 'Added by a later script', lambda: extra_plane(b))
                b.extrude('a_extrude', 'A extrude', s, NEW_BODY, distance='tall', body_name='A')
                b.fillet('a_round', 'A top round', lambda: [(top_edges(b, 'a_extrude'), '1 mm')], uses=('a_extrude',))
            with b.component('part_a_inner', 'Part A inner') as inner:
                s2 = b.sketch('inner_sketch', 'Inner outline', lambda: inner.xYConstructionPlane, rectangle('width', 'width'))
                b.extrude('inner_extrude', 'Inner extrude', s2, NEW_BODY, distance='tall', body_name='Inner')
    with b.component('part_b', 'Part B') as comp:
        if a_sketch_in_b:
            b.sketch('a_sketch', 'A outline', lambda: comp.xYConstructionPlane, rectangle('width', 'depth'), spec=(a_version,))
        s3 = b.sketch('b_sketch', 'B outline', lambda: comp.xYConstructionPlane, rectangle('depth', 'depth'), spec=(b_version,))
        b.extrude('b_extrude', 'B extrude', s3, NEW_BODY, distance='tall', body_name='B')
    if with_c:
        with b.component('part_c', 'Part C') as comp:
            s4 = b.sketch('c_sketch', 'C outline', lambda: comp.xYConstructionPlane, rectangle('width', 'width'))
            b.extrude('c_extrude', 'C extrude', s4, NEW_BODY, distance='tall', body_name='C')


def run(context):
    # ▶ from FusionUpsertTest.py. The runner calls main() itself.
    main({})


def main(args):
    app = adsk.core.Application.get()
    out = cad_apprentice.LiveLog(PROGRESS)
    results = []
    was_active = app.activeDocument
    with cad_apprentice.slow(out, 'new tab'):
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    des = adsk.fusion.Design.cast(app.activeProduct)
    des.designType = adsk.fusion.DesignTypes.ParametricDesignType
    root = des.rootComponent

    def check(label, ok):
        results.append(ok)
        out.append('%s  %s' % ('PASS' if ok else 'FAIL', label))

    def again(label, **kw):
        out.append('')
        out.append('-- ' + label)
        b = cad_apprentice.Builder(des, doc, out)
        try:
            describe(b, **kw)
            return b, b.finish(), None
        except Exception as err:
            with cad_apprentice.slow(out, 'marker to the end'):
                des.timeline.moveToEnd()
            cad_apprentice.close_groups(b.closed_groups)
            return b, False, str(err)

    # A collapsed group hides its steps, so open the groups to read them.
    def steps():
        closed = cad_apprentice.open_groups(des.timeline)
        found = [(x.name, x.healthState) for x in cad_apprentice.timeline_items(des.timeline)]
        cad_apprentice.close_groups(closed)
        return found

    def healthy():
        return [n for n, h in steps() if h == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState]

    def body(comp_key, b, name):
        return b.known[comp_key].component.bRepBodies.itemByName(name)

    def my_fillet():
        return [n for n, h in steps() if n == MY_FILLET]

    try:
        out.append('design intent: %s' % des.designIntent)

        b, ok, err = again('first build')
        check('first build finishes (%s)' % err, ok)
        check('nothing in the top component: %d sketches, %d bodies' % (root.sketches.count, root.bRepBodies.count), root.sketches.count == 0 and root.bRepBodies.count == 0)
        check('3 top-level parts: %d' % root.occurrences.count, root.occurrences.count == 3)
        check('4 occurrences with the nested one: %d' % root.allOccurrences.count, root.allOccurrences.count == 4)
        check('component named: %s' % b.known['part_a'].component.name, b.known['part_a'].component.name == 'Part A')
        check('nested part sits inside Part A', b.known['part_a'].component.occurrences.count == 1)
        check('A body is in Part A', body('part_a', b, 'A') is not None)
        check('sketches fully constrained, unresolved: %s' % b.unresolved(), not b.unresolved())
        check('sketch search reaches subcomponents', len([s for c in des.allComponents for s in c.sketches]) == 4)
        check('no top component note', not any('builds in the top component' in x for x in out))
        count = len(steps())
        a_volume = body('part_a', b, 'A').volume
        group_names = [g.name for g in des.timeline.timelineGroups]
        # Each part's loose steps go in a group named after it (lib/README.md); group('Part A') shares its name.
        check('one group per part: %s' % group_names, sorted(group_names) == ['Part A', 'Part A inner', 'Part B', 'Part C'])

        b, ok, err = again('rerun, no change')
        check('nothing created or changed: %s' % b.counts, ok and b.counts['created'] == 0 and b.counts['updated'] == 0 and b.counts['replaced'] == 0 and b.counts['removed'] == 0)
        check('still 3 parts and same timeline', root.occurrences.count == 3 and len(steps()) == count)

        # What a person would do by hand: a fillet in Part B that the script knows nothing about.
        comp_b = b.known['part_b'].component
        fi = comp_b.features.filletFeatures.createInput()
        fi.edgeSetInputs.addConstantRadiusEdgeSet(top_edges(b, 'b_extrude'), cad_apprentice.vi('1 mm'), False)
        with cad_apprentice.slow(out, 'hand-made fillet in Part B'):
            comp_b.features.filletFeatures.add(fi).name = MY_FILLET
        check('hand-made fillet added in Part B', len(my_fillet()) == 1)

        cad_apprentice.set_param(out, des.userParameters.itemByName('width'), '25 mm')
        cad_apprentice.catch_up(out)
        check('parameter moves the body in its part', body('part_a', b, 'A').volume > a_volume)
        cad_apprentice.set_param(out, des.userParameters.itemByName('width'), '20 mm')
        cad_apprentice.catch_up(out)

        b, ok, err = again('redraw the sketch in Part A', a_version='2')
        check('redraw finishes: %s, %s' % (b.counts, err), ok)
        check('redraw stayed in Part A', b.known['a_sketch'].parentComponent.name == 'Part A' and root.sketches.count == 0)
        check('hand-made fillet in Part B survives', len(my_fillet()) == 1 and not healthy())
        check('A body same size: %.4f vs %.4f' % (body('part_a', b, 'A').volume, a_volume), abs(body('part_a', b, 'A').volume - a_volume) < 0.0001)

        b, ok, err = again('step added at its spot', a_version='2', extra=True)
        order = [n for n, h in steps()]
        check('added step sits before the extrude: %s' % order, ok and order.index('Added by a later script') < order.index('A extrude'))
        check('added plane is in Part A', b.known['a_extra'].component.name == 'Part A')

        b, ok, err = again('step removed', a_version='2')
        check('step removed: %s' % b.counts, ok and b.counts['removed'] == 1 and not healthy())

        b, ok, err = again('script moves a step to another part', a_version='2', a_sketch_in_b=True)
        check('refused with a clear message: %s' % err, err is not None and 'Move it by hand' in err)
        check('nothing changed by the refusal', len(steps()) == count + 1 and not healthy())

        b, ok, err = again('Part C dropped', a_version='2', with_c=False)
        check('Part C and its steps removed: %s' % b.counts, ok and b.counts['removed'] == 3 and root.occurrences.count == 2)
        check('the other parts are fine', not healthy() and len(my_fillet()) == 1)

        b, ok, err = again('redraw under the hand-made fillet', a_version='2', with_c=False, b_version='2')
        check('run reports the break and does not pass: %s, %s' % (ok, err), not ok)
        check('the log names it', any('BROKEN' in x and MY_FILLET in x for x in out))
    except:
        out.append(traceback.format_exc())
        results.append(False)
    out.insert(0, 'RESULT: %d of %d passed' % (sum(1 for r in results if r), len(results)))
    out.append('DONE')
    open(LOG, 'w').write('\n'.join(out))
    with cad_apprentice.slow(out, 'close the tab without saving'):
        doc.close(False)
    out.close()
    if was_active and was_active.isValid:
        was_active.activate()
    fails = [x for x in out if x.startswith('FAIL') or x.startswith('Traceback')]
    return {'status': 'pass' if results and all(results) else 'fail', 'passed': sum(1 for r in results if r),
            'checks': len(results), 'fails': fails}
