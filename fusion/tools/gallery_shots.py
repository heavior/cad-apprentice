# Gallery pictures of a saved design: large views and close-ups. Run it through the CadApprenticeRunner add-in
# (fusion/rules.md § Gallery pictures). The saved design is never changed: it is
# inserted as a linked part into a new tab with its origin hidden (hiding the origin in the design's own tab
# marks it changed), the pictures are taken there, and the new tab is closed unsaved. args: doc (tab name of
# the saved design), out (folder), size [w, h], shots: a list of {name, eye [x,y,z] mm, target [x,y,z] mm,
# fov degrees (perspective) or extent mm (ortho), edges true/false, fit true to zoom to the whole model along
# eye→target, size [w, h] for this shot only}.
import math, os
import adsk.core, adsk.fusion
import cad_apprentice
from cad_apprentice import slow

P = adsk.core.Point3D.create


def main(args):
    app = adsk.core.Application.get()
    # The runner gives each request its own folder; tail -f its progress.log to watch a run.
    log = cad_apprentice.LiveLog(os.path.join(globals().get('OUT_DIR', args['out']), 'progress.log'))
    src = [d for d in app.documents if d.name == args['doc']][0]
    with slow(log, 'new tab'):
        tab = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    w, h = args.get('size', [2400, 1600])
    saved = []
    try:
        root = adsk.fusion.Design.cast(tab.products.itemByProductType('DesignProductType')).rootComponent
        with slow(log, 'insert %s' % src.name):
            occ = root.occurrences.addByInsert(src.dataFile, adsk.core.Matrix3D.create(), True)
        occ.component.isOriginFolderLightBulbOn = False
        root.isOriginFolderLightBulbOn = False
        with slow(log, 'let the tab draw'):
            for _ in range(20):  # without this the first picture caught the tab before it drew
                adsk.doEvents()
        vp = app.activeViewport
        vs = adsk.core.VisualStyles
        for s in args['shots']:
            vp.visualStyle = vs.ShadedWithVisibleEdgesOnlyVisualStyle if s.get('edges', True) else vs.ShadedVisualStyle
            cam = vp.camera
            cam.isSmoothTransition = False
            ex, ey, ez = (v / 10 for v in s['eye'])
            tx, ty, tz = (v / 10 for v in s['target'])
            cam.eye, cam.target = P(ex, ey, ez), P(tx, ty, tz)
            cam.upVector = adsk.core.Vector3D.create(0, 0, 1)
            if 'fov' in s:
                cam.cameraType = adsk.core.CameraTypes.PerspectiveCameraType
                cam.perspectiveAngle = math.radians(s['fov'])
                # Without this a shot after a fit kept the fit's zoom and came out blank.
                dist = math.dist((ex, ey, ez), (tx, ty, tz))
                cam.viewExtents = 2 * dist * math.tan(math.radians(s['fov']) / 2)
            else:
                cam.cameraType = adsk.core.CameraTypes.OrthographicCameraType
                cam.viewExtents = s['extent'] / 10
            cam.isFitView = bool(s.get('fit'))
            with slow(log, 'camera for %s' % s['name']):
                for _ in range(2):  # set once, the first shot of a run kept the new tab's own zoom
                    vp.camera = cam
                    for _ in range(5):
                        adsk.doEvents()
            vp.refresh()
            f = os.path.join(args['out'], s['name'] + '.png')
            with slow(log, 'picture %s' % s['name']):
                vp.saveAsImageFile(f, *s.get('size', [w, h]))
            saved.append(f)
    finally:
        with slow(log, 'close the tab'):
            tab.close(False)
        src.activate()
        log.close()
    return {'saved': saved, 'source modified': src.isModified}
