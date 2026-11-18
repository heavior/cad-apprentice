# Builds __DOC__ through the cad_apprentice library, so running it again updates the design and keeps
# what it didn't make. Made by `fusion_outputs.py new` as a starting point: a rounded block. Replace
# PARAMS, the draw functions and describe() with the real design.
# How to write steps, and how to read a failed run: cad-apprentice/fusion/lib/README.md.
# The entry file passes OUT_DIR (the log and pictures go there), MODE and NAME.
# MODE: 'new' builds in a new tab and saves it as a new design; for the first build only. 'saved'
# updates the saved design and saves a new version: the normal round. 'clean' wipes the saved design's
# timeline and builds it all again. 'check' is 'saved' plus a rerun that should change nothing and the
# parameter test; 'night' builds in a new tab and does the same checks, but never saves: save the tab
# by hand if you like it. 'check:width,height' tries only those parameters;
# 'check:random=50' adds 50 random sets (fusion/lib/README.md, The parameter test).
# The API works in centimetres. Sizes in expressions are in mm.
import os, traceback
import adsk.core, adsk.fusion
import cad_apprentice
from cad_apprentice.helpers import (H, V, p3, sketch_tools, report_sketch, axis, rectangle_n, flat_face, face_edges, camera, planes_off,
                                   hide_sketches, saved_design, wipe, write_stl)

MODE, ONLY, TEST = cad_apprentice.split_mode(MODE)
LOG = os.path.join(OUT_DIR, NAME + '.log')
SAVED_DOC = '__DOC__'
# A lineage urn, to pick one file when two saved designs share the name. None takes the newest.
SAVED_ID = None
SAVE_NOTE = 'Script update.'
# STLs only once the person has approved the design for printing (3dprinting/rules.md).
MAKE_STL = False
New = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
Z = (0, 0, 1)

# (name, expression, unit, comment, favorite, (low, high, step)). Favorites show in MakerWorld's
# Customize and must be plain values, never formulas. Every size the design uses is a parameter here.
# Every plain value gets a range: the values it is meant to take, guessed on the wide side and offered
# to the person for review (fusion/rules.md rule 19). The parameter test tries them, and they are the
# favorites' slider limits. A formula gets None.
PARAMS = [
    ('block_width', '40 mm', 'mm', 'block size along X', True, ('20 mm', '80 mm', '5 mm')),
    ('block_depth', '20 mm', 'mm', 'block size along Y', True, ('10 mm', '40 mm', '5 mm')),
    ('block_height', '10 mm', 'mm', 'block height', False, ('5 mm', '30 mm', '5 mm')),
    ('block_round_radius', '2 mm', 'mm', 'round on the top edges', False, ('0.5 mm', '4 mm', '0.5 mm')),
]
# The favorites in the order Customize shows them.
FAV_ORDER = [p[0] for p in PARAMS if p[4]]


def draw_outline(s, comp, out):
    # The block seen from above: a rectangle centred on the origin. Every sketch ends fully
    # constrained, with its sizes tied to parameters; report_sketch logs what is still loose.
    refused, attempt, size, gc, dims = sketch_tools(s)
    x_ax, y_ax = axis(s, comp.xConstructionAxis), axis(s, comp.yConstructionAxis)
    pt = lambda x, y: s.sketchPoints.add(p3(x, y))
    corners = [pt(-2, -1), pt(2, -1), pt(2, 1), pt(-2, 1)]
    bottom, right, top, left = rectangle_n(s, corners)
    attempt('bottom straight', lambda: gc.addHorizontal(bottom))
    attempt('top straight', lambda: gc.addHorizontal(top))
    attempt('right square', lambda: gc.addVertical(right))
    # Symmetry also squares the left side.
    attempt('centred across', lambda: gc.addSymmetry(corners[0], corners[1], y_ax))
    attempt('centred along', lambda: gc.addSymmetry(corners[0], corners[3], x_ax))
    size('width', lambda: dims.addDistanceDimension(corners[0], corners[1], H, p3(0, -1.5)), 'block_width')
    size('depth', lambda: dims.addDistanceDimension(corners[0], corners[3], V, p3(-2.5, 0)), 'block_depth')
    report_sketch(s, refused, out)


def describe(b):
    out = b.log
    um = b.des.unitsManager
    um.distanceDisplayUnits = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
    for name, expr, unit, comment, fav, r in [p for n in FAV_ORDER for p in PARAMS if p[0] == n] + [p for p in PARAMS if not p[4]]:
        b.param(name, expr, unit, comment, favorite=fav, range=r and r[:2], step=r and r[2])
    root = b.des.rootComponent
    with b.group('Block'):
        sk = b.sketch('outline_sketch', 'Block outline', lambda: root.xYConstructionPlane, lambda s: draw_outline(s, root, out),
                      spec=(draw_outline,))
        b.extrude('block_extrude', 'Block extrude', sk, New, distance='block_height', body_name='Block')
        b.fillet('block_round', 'Block top round',
                 lambda: [(face_edges(flat_face(b.body('block_extrude'), Z, um.evaluateExpression('block_height', 'cm')), True),
                           'block_round_radius')], uses=['block_extrude'])


def pictures(app, des, out):
    # One view of the whole design. Add a view per part as the design grows.
    vp = app.activeViewport
    planes = planes_off(des)
    with cad_apprentice.slow(out, 'picture model_iso'):
        camera(vp, p3(0, 0, 0), (-10, -10, 7), Z)
        vp.saveAsImageFile(os.path.join(OUT_DIR, 'view_model_iso.png'), 1600, 1200)
    for x, on in planes:
        x.isLightBulbOn = on


def stls(des, out):
    # One STL per printed part, named after it. write_stl always exports at High mesh refinement.
    write_stl(des, out, des.rootComponent.bRepBodies.itemByName('Block'), os.path.join(OUT_DIR, 'block.stl'))
    out.append('stl exported')


def run(context):
    out = cad_apprentice.LiveLog(LOG)
    app = adsk.core.Application.get()
    b = go_back = None
    try:
        if MODE in ('saved', 'check', 'clean'):
            doc = saved_design(app, out, SAVED_DOC, SAVED_ID)
            doc.activate()
            des = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
            if MODE == 'clean':
                go_back = wipe(doc, des, out, FAV_ORDER)  # A failed rebuild goes back to before the wipe.
        else:
            # A first build only: a second 'new' would save a second design of the same name. 'night' saves nothing.
            if MODE == 'new' and any(f.name == SAVED_DOC for f in app.data.activeProject.rootFolder.dataFiles):
                raise Exception('%s is already saved in %s; run saved, or rename it first' % (SAVED_DOC, app.data.activeProject.name))
            with cad_apprentice.slow(out, 'new tab'):
                doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
            des = adsk.fusion.Design.cast(app.activeProduct)
            des.designType = adsk.fusion.DesignTypes.ParametricDesignType
        b = cad_apprentice.Builder(des, doc, out, go_back_to=go_back)
        cad_apprentice.progress(out, 'mode %s: building' % MODE)
        describe(b)
        if not b.finish():
            out.close()
            return
        hide_sketches(des, out)
        pictures(app, des, out)
        if MAKE_STL:
            stls(des, out)
        if MODE in ('saved', 'check', 'clean'):
            b.save(SAVE_NOTE)
        elif MODE == 'new':
            # A first build is saved as a new design (fusion/rules.md rule 4).
            with cad_apprentice.slow(out, 'save as %s' % SAVED_DOC):
                doc.saveAs(SAVED_DOC, app.data.activeProject.rootFolder, 'Built by the %s script.' % NAME, '')
            out.append('saved as %s in %s' % (SAVED_DOC, app.data.activeProject.name))
        else:
            out.append('night: not saved; the tab stays open, save it by hand if you like it')
        if MODE in ('check', 'night'):
            out.append('--- rerun, should change nothing')
            b = cad_apprentice.Builder(des, doc, out)
            describe(b)
            if not b.finish():
                out.close()
                return
            if b.structure_changed or b.params_set:
                out.append('RERUN CHANGED SOMETHING, see the steps line above')
            if not b.trials(only=ONLY, stop=os.path.join(OUT_DIR, 'stop'), **TEST):
                b.abort('a trial did not come back')
                out.close()
                return
            for item in b.trials_failed:
                out.append('TRIAL FAILED: ' + item)
            b.back_to_saved()
        out.append('DONE')
    except:
        out.append(traceback.format_exc())
        if b:
            b.abort('see the error above')
    out.close()
