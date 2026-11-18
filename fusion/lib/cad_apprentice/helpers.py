# Helpers every design script used to copy in. A script imports the ones it needs:
#   from cad_apprentice.helpers import mm, p3, sketch_tools, report_sketch, flat_face
# A copy that differs gets a parameter here, not a second version in the script.
import os, re
import adsk.core, adsk.fusion
from . import slow, timeline_items


# ---------- Numbers and points ----------

# Fusion's API works in cm: v as mm, rounded to 0.01.
def mm(v):
    return round(v * 10, 2)


# A Point3D, in cm like the rest of the API.
def p3(x, y, z=0.0):
    return adsk.core.Point3D.create(x, y, z)


# A bounding box as text in mm: 'x 0.0..20.0  y 0.0..10.0  z 0.0..5.0'.
def box(b, digits=1):
    f = '%%.%df' % digits
    return ('x {0}..{0}  y {0}..{0}  z {0}..{0}'.format(f)) % (mm(b.minPoint.x), mm(b.maxPoint.x), mm(b.minPoint.y), mm(b.maxPoint.y), mm(b.minPoint.z), mm(b.maxPoint.z))


# ---------- Sketches ----------

# Logs a sketch's state: fully constrained or not, its counts, what was refused, and which
# curves and points are still loose.
def report_sketch(s, refused, out):
    out.append('sketch %s: fully constrained %s, %d dimensions, %d constraints, %d profile(s)' % (
        s.name, s.isFullyConstrained, s.sketchDimensions.count, s.geometricConstraints.count, s.profiles.count))
    for item in refused:
        out.append('  refused: ' + item)
    if not s.isFullyConstrained:
        loose = [c.objectType.split('::')[-1] for c in s.sketchCurves if not c.isFullyConstrained]
        loose += ['point %.2f,%.2f' % (mm(q.geometry.x), mm(q.geometry.y)) for q in s.sketchPoints if not q.isFullyConstrained]
        out.append('  still loose: %s' % ', '.join(loose))


def trying(refused):
    # Runs one constraint or dimension. A refusal goes in the log and the sketch report, not fatal.
    def attempt(label, fn):
        try:
            return fn()
        except Exception as err:
            refused.append('%s (%s)' % (label, str(err).split(' - ')[-1].strip()))
    return attempt


def sizer(s, attempt):
    # size(label, add, expr): add() makes a dimension, which then takes expr.
    def size(label, add, expr):
        attempt(label, lambda: setattr(add().parameter, 'expression', expr))
    return size


def sketch_tools(s):
    # refused, attempt, size, constraints, dimensions: what every draw_ function starts with.
    refused = []
    attempt = trying(refused)
    return refused, attempt, sizer(s, attempt), s.geometricConstraints, s.sketchDimensions


def to_sk(s, x, y, z=0.0):
    # A model point in the sketch's own 2D space.
    q = s.modelToSketchSpace(p3(x, y, z))
    return p3(q.x, q.y)


def projected(s, entity):
    # A projected line can split the profiles it crosses, so it is construction only.
    q = s.project(entity).item(0)
    if hasattr(q, 'isConstruction'):
        q.isConstruction = True
    return q


def axis(s, construction_axis):
    # A construction axis brought into the sketch as a construction line.
    line = s.project(construction_axis).item(0)
    line.isConstruction = True
    return line


def rectangle_n(s, corners):
    # A closed outline through the sketch points, in order. Returns the lines.
    lines = s.sketchCurves.sketchLines
    return [lines.addByTwoPoints(corners[i], corners[(i + 1) % len(corners)]) for i in range(len(corners))]


H = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
V = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation


def flat_in(s, d):
    # True if the model direction d runs along the sketch's horizontal.
    a, q = to_sk(s, 0, 0, 0), to_sk(s, *d)
    return abs(q.x - a.x) > abs(q.y - a.y)


# H or V: the dimension direction that runs along the model direction d in this sketch.
def along(s, d):
    return H if flat_in(s, d) else V


# Makes line horizontal or vertical, whichever runs along the model direction d.
def keep_along(s, line, d):
    gc = s.geometricConstraints
    return gc.addHorizontal(line) if flat_in(s, d) else gc.addVertical(line)


def level_along(s, a, b, d):
    # Puts points a and b on one line along the model direction d.
    gc = s.geometricConstraints
    return gc.addHorizontalPoints(a, b) if flat_in(s, d) else gc.addVerticalPoints(a, b)


# All the sketch's profiles in one collection.
def every_profile(s):
    c = adsk.core.ObjectCollection.create()
    for p in s.profiles:
        c.add(p)
    return c


# ---------- Bodies and faces ----------

def flat_face(body, normal, at):
    # The biggest flat face whose outward normal is the given axis vector, at that coordinate (cm).
    # Biggest, because tube ends and stud tops can face the same way at the same height.
    n = adsk.core.Vector3D.create(*normal)
    found = []
    for f in body.faces:
        pl = adsk.core.Plane.cast(f.geometry)
        if not pl:
            continue
        ok, nv = f.evaluator.getNormalAtPoint(f.pointOnFace)
        q = f.pointOnFace
        if ok and nv.isParallelTo(n) and nv.dotProduct(n) > 0 and abs(q.x * normal[0] + q.y * normal[1] + q.z * normal[2] - at) < 1e-5:
            found.append(f)
    if not found:
        bb = lambda x: tuple(mm(v) for v in (x.boundingBox.minPoint.x, x.boundingBox.maxPoint.x, x.boundingBox.minPoint.y,
                                             x.boundingBox.maxPoint.y, x.boundingBox.minPoint.z, x.boundingBox.maxPoint.z))
        seen = ['%s %.0f mm3 x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f' % ((x.name, x.volume * 1000) + bb(x))
                for x in body.parentComponent.bRepBodies]
        raise Exception('no flat face facing %s at %.2f mm on %s; bodies: %s' % (normal, mm(at), body.name, '; '.join(seen)))
    return max(found, key=lambda f: f.area)


# A face's edges: the outer loop only, or every loop, holes included.
def face_edges(face, outer_only):
    found = adsk.core.ObjectCollection.create()
    for loop in face.loops:
        if loop.isOuter or not outer_only:
            for e in loop.edges:
                found.add(e)
    return found


def main_body(comp, name):
    # The part by name. A cut that splits it leaves pieces named 'name (1)' and so on, and the name can
    # move to a piece, so take the biggest.
    piece = re.compile(re.escape(name) + r' \(\d+\)$')
    found = [x for x in comp.bRepBodies if x.name == name or piece.match(x.name)]
    return max(found, key=lambda x: x.volume) if found else None


def loose_pieces(des, names=None):
    # Components with more than one body: a cut broke a piece off, or a join missed one. names: only those.
    return ['%s: %d bodies' % (c.name, c.bRepBodies.count) for c in des.allComponents
            if c.bRepBodies.count > 1 and (names is None or c.name in names)]


# ---------- Views and pictures ----------

def camera(vp, target, eye, up, extent=None):
    # target: a Point3D. eye: where the eye sits, as (dx, dy, dz) from target. extent: the view's width
    # in cm around target; without it the view fits everything shown.
    cam = vp.camera
    cam.isSmoothTransition = False
    cam.cameraType = adsk.core.CameraTypes.OrthographicCameraType
    cam.target = target
    cam.eye = p3(target.x + eye[0], target.y + eye[1], target.z + eye[2])
    cam.upVector = adsk.core.Vector3D.create(*up)
    if extent:
        cam.viewExtents = extent
    vp.camera = cam
    if not extent:
        vp.fit()
    adsk.doEvents()
    vp.refresh()


def planes_off(des):
    # Construction planes, axes and points hidden for the pictures. Returns what to put back.
    planes = [(x, x.isLightBulbOn) for c in des.allComponents
              for x in list(c.constructionPlanes) + list(c.constructionAxes) + list(c.constructionPoints)]
    for x, _ in planes:
        x.isLightBulbOn = False
    return planes


def hide_sketches(des, out):
    # Every sketch hidden when the build ends. A sketch point far from the model makes Fusion zoom out to
    # it (fusion/rules.md rule 14).
    for c in des.allComponents:
        for s in c.sketches:
            s.isVisible = False
    out.append('sketches hidden')


def sketch_pictures(app, des, out, out_dir):
    # Each sketch alone, seen square on, with its dimensions and constraints showing, saved as
    # out_dir/sketch_<name>.png. Bodies, planes and the other sketches are hidden for it and put back.
    vp = app.activeViewport
    bodies = [(x, x.isLightBulbOn) for c in des.allComponents for x in c.bRepBodies]
    sketches = [(x, x.isVisible) for c in des.allComponents for x in c.sketches]
    planes = planes_off(des)
    for x, _ in bodies:
        x.isLightBulbOn = False
    for s, _ in sketches:
        s.isVisible = False
    for s, _ in sketches:
        s.isVisible = True
        s.areDimensionsShown = True
        s.areConstraintsShown = True
        normal = s.xDirection.crossProduct(s.yDirection)
        with slow(out, 'picture of sketch %s' % s.name):
            camera(vp, s.origin, (normal.x * 200, normal.y * 200, normal.z * 200), (s.yDirection.x, s.yDirection.y, s.yDirection.z))
            vp.saveAsImageFile(os.path.join(out_dir, 'sketch_%s.png' % s.name.lower().replace(' ', '_')), 1600, 1200)
        s.isVisible = False
    for s, seen in sketches:
        s.isVisible = seen
    for x, on in bodies + planes:
        x.isLightBulbOn = on
    out.append('sketch pictures saved')


# ---------- The run's report ----------

def report(des, out, bodies=None):
    # The end of a build's log: each sketch and its dimensions, the timeline with its health, each body's
    # size, the occurrences and the favorites. bodies: (label, body) pairs; by default every body,
    # labelled "component / body".
    for c in des.allComponents:
        for s in c.sketches:
            out.append('sketch %s: fully constrained %s' % (s.name, s.isFullyConstrained))
            for d in s.sketchDimensions:
                out.append('    %s = %.2f' % (d.parameter.expression, d.parameter.value * 10))
    out.append('timeline:')
    for it in timeline_items(des.timeline):
        ok = it.healthState == adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState
        out.append('%s%s (%s)%s' % ('    ' if it.parentGroup else '  ', it.name, it.entity.objectType.split('::')[-1], '' if ok else ' NOT HEALTHY: ' + it.errorOrWarningMessage))
    if bodies is None:
        bodies = [('%s / %s' % (c.name, x.name), x) for c in des.allComponents for x in c.bRepBodies]
    for label, x in bodies:
        out.append('body %s: solid %s, volume %.1f mm3, faces %d, %s' % (label, x.isSolid, x.volume * 1000, x.faces.count, box(x.boundingBox)))
    out.append('occurrences: %s' % ', '.join(o.name for o in des.rootComponent.occurrences))
    ps = des.userParameters
    out.append('favorites: %s' % ', '.join(ps.item(i).name for i in range(ps.count) if ps.item(i).isFavorite))


# ---------- STL files ----------

def write_stl(des, out, what, path):
    # One STL, always at High mesh refinement, Fusion's finest preset, so curves print smooth. what: a
    # body, an occurrence or a component. precheck stops a script that exports an STL any other way.
    em = des.exportManager
    opts = em.createSTLExportOptions(what, path)
    opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
    with slow(out, 'export %s' % os.path.basename(path)):
        em.execute(opts)


# ---------- The saved design ----------

def saved_design(app, out, name, file_id=None):
    # The newest design named name, the one each 'saved' round updates. Opened if it isn't.
    # file_id (a lineage urn) picks one file exactly, for when two files share the name: the newest is
    # then not always the right one (seen with two "Suspension bridge" files).
    # Only the exact name: a run for "Bracket" must never update, or clean, "Bracket holder".
    files = [f for f in app.data.activeProject.rootFolder.dataFiles if f.name == name]
    if file_id:
        files = [f for f in files if f.id == file_id]
    if not files:
        raise Exception('no saved %s%s in %s' % (name, ' with id ' + file_id if file_id else '', app.data.activeProject.name))
    first = max(files, key=lambda f: f.dateCreated)
    for d in app.documents:
        # An unsaved tab can throw "Failed to get temporary file" here, so skip it.
        try:
            same = d.dataFile and d.dataFile.id == first.id
        except RuntimeError:
            same = False
        if same:
            return d
    with slow(out, 'open %s' % first.name):
        return app.documents.open(first)


def wipe(doc, des, out, fav_order=(), old_names=None):
    # The 'clean' round: the whole timeline goes, then every step is made new. Faster than updating
    # every step in place. The saved
    # versions keep the old one. The user parameters stay; the build sets them again. The favorites are
    # put in fav_order on the way. Returns the version a failed build goes back to: Builder(go_back_to=),
    # or the go-back would open the wiped design. None for a design never saved.
    back = doc.dataFile.latestVersionNumber if doc.dataFile else None
    if doc.isModified:
        # Unsaved changes, maybe the person's: kept in a version of their own before anything goes.
        with slow(out, 'clean: save a restore point'):
            saved = doc.save('Restore point before a clean rebuild')
        if not saved:
            raise Exception('could not save a restore point of the unsaved changes, so nothing was wiped')
        back = back + 1 if back is not None else None
    tl = des.timeline
    n = tl.count
    with slow(out, 'clean: delete %d timeline items' % n):
        tl.markerPosition = 0
        tl.deleteAllAfterMarker()
    root = des.rootComponent
    left = [o for o in root.occurrences] + [x for x in root.bRepBodies]
    with slow(out, 'clean: delete %d leftover components or bodies' % len(left)):
        for x in left:
            x.deleteMe()
    out.append('clean: deleted %d timeline items and %d leftover components or bodies' % (n, len(left)))
    if fav_order:
        order_favorites(des, out, fav_order, old_names)
    return back


def order_favorites(des, out, fav_order, old_names=None):
    # A design keeps the order its parameters were first made in, and MakerWorld's Customize shows the
    # favorites in that order. With the timeline gone only other parameters use them, so each favorite,
    # in fav_order, is made again at the end with its current value (the person's, if they changed it), and the
    # parameters that used the old one are pointed at the new one. One still under its old_names name
    # is made under its new name the same way.
    old_names = old_names or {}
    ps = des.userParameters
    if [ps.item(i).name for i in range(ps.count) if ps.item(i).isFavorite] == list(fav_order):
        return
    with slow(out, 'clean: put the favorites in order'):
        for name in fav_order:
            # Fusion refuses itemByName(''), so look up an old name only when there is one.
            old = ps.itemByName(name) or (ps.itemByName(old_names[name]) if name in old_names else None)
            if old is None:  # a new favorite: the build makes it, after the ones moved here
                continue
            expr, unit, comment = old.expression, old.unit, old.comment
            was_name = name + '_was'
            old.name = was_name  # Fusion rewrites the expressions that use it
            new = ps.add(name, adsk.core.ValueInput.createByString(expr), unit, comment)
            new.isFavorite = True
            was = re.compile(r'\b%s\b' % re.escape(was_name))
            for i in range(ps.count):
                q = ps.item(i)
                if was.search(q.expression):
                    q.expression = was.sub(name, q.expression)
            if not old.deleteMe():
                raise Exception('clean: %s is still in use, so the favorites could not be put in order' % was_name)
    out.append('clean: favorites now in order: %s' % ', '.join(ps.item(i).name for i in range(ps.count) if ps.item(i).isFavorite))
