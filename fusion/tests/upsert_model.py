# The small test model for the cad_apprentice scenarios (upsert-test-scenarios.md § 1): a component with
# a nested one inside it, and steps in the top component, with every feature type the library has.
# describe(b, v) builds variant v. variant() gives the defaults; each scenario changes a few knobs.
import re
import adsk.core, adsk.fusion
import cad_apprentice
from cad_apprentice import vi, tag, tagged

NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
H = adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation
V = adsk.fusion.DimensionOrientations.VerticalDimensionOrientation
EPS = 1e-4  # cm

PARAMS = [
    ('base_w', '40 mm', 'mm', 'Base width', True),
    ('base_d', '30 mm', 'mm', 'Base depth', True),
    ('base_h', '10 mm', 'mm', 'Base height', True),
    ('wall', '3 mm', 'mm', 'Post and rib width', False),
    ('hole_d', '6 mm', 'mm', 'Hole diameter', False),
    ('hole_n', '4', '', 'Number of holes', False),
    ('round_r', '1 mm', 'mm', 'Round radius', False),
    ('post_h', 'base_h * 2', 'mm', 'Post height', False),
    ('pitch', 'base_w / 4', 'mm', 'Hole spacing', False),
    ('plane_off', 'base_h + 5 mm', 'mm', 'Cap plane height', False),
]

LABELS = {
    'outer': 'Outer', 'inner': 'Inner',
    'base_sketch': 'Base outline', 'base': 'Base extrude', 'top_plane': 'Top plane',
    'hole_sketch': 'Hole outline', 'hole_cut': 'Hole cut', 'hole_pattern': 'Hole pattern',
    'post_sketch': 'Post outline', 'post': 'Post join', 'rib_sketch': 'Rib outline', 'rib': 'Rib extrude',
    'rib_join': 'Rib combine', 'round': 'Rounds', 'chamfer': 'Back chamfer', 'mark_sketch': 'Corner mark',
    'block_sketch': 'Block outline', 'block': 'Block extrude', 'block_move': 'Block move', 'stock': 'Stock',
    'cap_plane': 'Cap plane', 'cap_sketch': 'Cap outline', 'cap': 'Cap extrude',
    'mid_plane': 'Middle plane', 'first_plane': 'First plane', 'slab': 'Slab', 'slab_cut': 'Slab cut',
    'rib_peek': 'Rib peek', 'boom': 'Boom', 'inner_copies': 'Inner copies', 'solo_plane': 'Solo plane',
    'hole_rounds': 'Hole rounds',
}

ORDER = ['base_sketch', 'base', 'top_plane', 'hole_sketch', 'hole_cut', 'hole_pattern', 'post_sketch', 'post',
         'rib_sketch', 'rib', 'rib_join', 'round', 'chamfer', 'mark_sketch']
INNER = ['block_sketch', 'block', 'block_move', 'stock']
CAP = ['cap_plane', 'cap_sketch', 'cap']

RIB_SCALE = '1'  # read by the rib's draw function as a global (C4)


def variant(**kw):
    v = {
        'params': [dict(name=n, expr=e, unit=u, comment=c, favorite=f) for n, e, u, c, f in PARAMS],
        'rename': {},  # old parameter name -> new, for every expression in the model (B5-B7)
        'names': {},  # key -> label, over LABELS
        'order': list(ORDER),  # the Outer steps; ('group', name, [keys]) puts some in a group
        'inner_order': list(INNER),
        'cap_order': list(CAP),
        'with_inner': True, 'with_cap': True, 'top_first': [],
        'spec': {}, 'uses': {}, 'alt': {},  # per key: extra spec, a uses override, a code variant
        'base_draw': base_outline, 'post_draw': rectangle,
        'base_dist': 'base_h', 'base_body': 'Base', 'rib_sym': 'base_d', 'rib_w': 'wall',
        'hole_op': CUT, 'post_dist': 'post_h', 'combine_op': JOIN,
        'round_r': ('round_r', 'round_r'), 'chamfer_d': 'round_r',
        'pattern': ('hole_n', 'pitch', '1', '1 mm'), 'pattern_adjust': False,
        'move': ('base_w + 10 mm', '0 mm', '0 mm'),
        'top_off': 'base_h', 'cap_off': 'plane_off',
        'die_at': None,  # raise right after this step (D6, K6)
        'inner_copies': None,  # (count, spacing): a pattern of the Inner occurrence (I4)
        'hole_y': 'base_d / 2',  # 'base_d' puts the holes on the back edge, so they cut it (L3)
    }
    v.update(kw)
    return v


def E(v, expr):
    for old, new in v['rename'].items():
        expr = re.sub(r'\b%s\b' % re.escape(old), new, expr)
    return expr


def label(v, key):
    return v['names'].get(key, LABELS[key])


def point(x, y):
    return adsk.core.Point3D.create(x, y, 0)


def rectangle(width, depth):
    def draw(s):  # slow-ok: the sketch step's "make" line covers it
        lines = s.sketchCurves.sketchLines.addTwoPointRectangle(point(0, 0), point(2, 2))
        gc = s.geometricConstraints
        gc.addCoincident(lines.item(0).startSketchPoint, s.originPoint)
        gc.addHorizontal(lines.item(0))
        gc.addVertical(lines.item(1))
        gc.addHorizontal(lines.item(2))
        gc.addVertical(lines.item(3))
        dims = s.sketchDimensions
        dims.addDistanceDimension(lines.item(0).startSketchPoint, lines.item(0).endSketchPoint, H, point(1, -1)).parameter.expression = width
        dims.addDistanceDimension(lines.item(1).startSketchPoint, lines.item(1).endSketchPoint, V, point(3, 1)).parameter.expression = depth
        return lines
    return draw


# A helper the base outline calls (C3 swaps its code).
def corner_tag(lines):
    tag(lines.item(1).endSketchPoint, 'corner')


def base_outline(width, depth):
    def draw(s):
        lines = rectangle(width, depth)(s)
        corner_tag(lines)
    return draw


# The same outline, drawn by other code (C2).
def base_outline_v2(width, depth):
    def draw(s):  # slow-ok: the sketch step's "make" line covers it
        lines = s.sketchCurves.sketchLines.addTwoPointRectangle(point(0, 0), point(3, 3))
        gc = s.geometricConstraints
        gc.addCoincident(lines.item(0).startSketchPoint, s.originPoint)
        for i in (0, 2):
            gc.addHorizontal(lines.item(i))
        for i in (1, 3):
            gc.addVertical(lines.item(i))
        dims = s.sketchDimensions
        dims.addDistanceDimension(lines.item(1).startSketchPoint, lines.item(1).endSketchPoint, V, point(4, 1)).parameter.expression = depth
        dims.addDistanceDimension(lines.item(0).startSketchPoint, lines.item(0).endSketchPoint, H, point(1, -1)).parameter.expression = width
        corner_tag(lines)
    return draw


def make_fn(src, name):
    # Compiles a function into this module, so its globals are this module's (C3, C5).
    exec(compile(src, '<scenario %s>' % name, 'exec'), globals())
    return globals()[name]


def circle(x, y, d):
    def draw(s):  # slow-ok: the sketch step's "make" line covers it
        c = s.sketchCurves.sketchCircles.addByCenterRadius(point(0.5, 0.5), 0.3)
        dims = s.sketchDimensions
        dims.addDiameterDimension(c, point(1, 1)).parameter.expression = d
        dims.addDistanceDimension(s.originPoint, c.centerSketchPoint, H, point(0.25, -0.5)).parameter.expression = x
        dims.addDistanceDimension(s.originPoint, c.centerSketchPoint, V, point(-0.5, 0.25)).parameter.expression = y
    return draw


def rib_outline(width, height):
    def draw(s):
        rectangle('(%s) * %s' % (width, RIB_SCALE), height)(s)
    return draw


def mark_draw(b, d):
    def draw(s):  # slow-ok: the sketch step's "make" line covers it
        corner = tagged(b.known['base_sketch'], 'corner')
        p = s.project(corner).item(0)
        c = s.sketchCurves.sketchCircles.addByCenterRadius(p, 0.15)
        s.sketchDimensions.addDiameterDimension(c, point(5, 5)).parameter.expression = d
    return draw


def edges(body, test):
    c = adsk.core.ObjectCollection.create()
    bb = body.boundingBox
    for e in body.edges:
        if test(e.boundingBox, bb):
            c.add(e)
    return c


def post_top(body):
    return edges(body, lambda e, bb: e.minPoint.z > bb.maxPoint.z - EPS)


def post_top_x(body):  # only the post's top edges along x
    return edges(body, lambda e, bb: e.minPoint.z > bb.maxPoint.z - EPS and e.maxPoint.y - e.minPoint.y < EPS)


def corner_edge(body):  # the upright edge at x max, y = 0
    return edges(body, lambda e, bb: e.minPoint.x > bb.maxPoint.x - EPS and abs(e.minPoint.y) < EPS and abs(e.maxPoint.y) < EPS and e.maxPoint.z - e.minPoint.z > EPS)


def hole_tops(body, height):  # L3: the top edge of every hole, a circle at the base's top face
    c = adsk.core.ObjectCollection.create()
    for e in body.edges:
        bb = e.boundingBox
        if e.geometry.curveType == adsk.core.Curve3DTypes.Circle3DCurveType and abs(bb.minPoint.z - height) < EPS and abs(bb.maxPoint.z - height) < EPS:
            c.add(e)
    return c


def back_bottom(body):  # the bottom edge at the back, y max, z = 0
    return edges(body, lambda e, bb: e.minPoint.y > bb.maxPoint.y - EPS and abs(e.minPoint.z) < EPS and abs(e.maxPoint.z) < EPS)


def back_bottom_v2(body):
    found = adsk.core.ObjectCollection.create()
    top_y = body.boundingBox.maxPoint.y
    for e in body.edges:
        bb = e.boundingBox
        if min(bb.minPoint.y, bb.maxPoint.y) > top_y - EPS and max(abs(bb.minPoint.z), abs(bb.maxPoint.z)) < EPS:
            found.add(e)
    return found


def first_hole_or_back(body):  # G2: the first hole's top edge once the holes are cut, else the back bottom edge
    holes = [e for e in body.edges if e.geometry.curveType == adsk.core.Curve3DTypes.Circle3DCurveType]
    if not holes:
        return back_bottom(body)
    top = max(e.boundingBox.maxPoint.z for e in holes)
    first = min((e for e in holes if e.boundingBox.maxPoint.z > top - EPS), key=lambda e: e.boundingBox.minPoint.x)
    c = adsk.core.ObjectCollection.create()
    c.add(first)
    return c


def stock_box():
    box = adsk.core.OrientedBoundingBox3D.create(adsk.core.Point3D.create(-3, 0, 0.5), adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0), 1, 1, 1)
    return adsk.fusion.TemporaryBRepManager.get().createBox(box)


def slab_box():
    box = adsk.core.OrientedBoundingBox3D.create(adsk.core.Point3D.create(0.5, 1.5, -1), adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0), 1.2, 1.2, 1)
    return adsk.fusion.TemporaryBRepManager.get().createBox(box)


def offset_plane(comp, base, off):
    def make():  # slow-ok: the step's "make" line covers it
        pi = comp.constructionPlanes.createInput()
        pi.setByOffset(base(), vi(off))
        return comp.constructionPlanes.add(pi)
    make.offset = lambda: off
    return make


def plain_plane(comp, off):
    def make():  # slow-ok: the step's "make" line covers it
        pi = comp.constructionPlanes.createInput()
        pi.setByOffset(comp.xYConstructionPlane, vi(off))
        return comp.constructionPlanes.add(pi)
    return make


def kw(v, key):
    return dict(spec=v['spec'].get(key, ()), uses=v['uses'].get(key, DEFAULT_USES.get(key, ())))


DEFAULT_USES = {
    'hole_cut': ('base',), 'hole_pattern': ('hole_cut',), 'post': ('base',), 'rib_join': ('base', 'rib'),
    'round': ('base', 'post', 'rib_join'), 'chamfer': ('base', 'round'), 'mark_sketch': ('base_sketch', 'top_plane'),
    'post_sketch': ('top_plane',), 'block_move': ('block',), 'cap_sketch': ('cap_plane',), 'slab_cut': ('slab',),
    'inner_copies': ('inner',), 'hole_rounds': ('hole_pattern',),
}


def step_table():
    def base_sketch(b, v, S):
        comp = S['comp']
        S['base_sketch'] = b.sketch('base_sketch', label(v, 'base_sketch'), lambda: comp.xYConstructionPlane, v['base_draw'](E(v, 'base_w'), E(v, 'base_d')), **kw(v, 'base_sketch'))

    def base(b, v, S):
        b.extrude('base', label(v, 'base'), S['base_sketch'], NEW, distance=E(v, v['base_dist']), body_name=v['base_body'], **kw(v, 'base'))

    def top_plane(b, v, S):
        comp = S['comp']
        make = offset_plane(comp, lambda: comp.xYConstructionPlane, E(v, v['top_off']))
        b.plane('top_plane', label(v, 'top_plane'), make, **kw(v, 'top_plane'))

    def hole_sketch(b, v, S):
        comp = S['comp']
        S['hole_sketch'] = b.sketch('hole_sketch', label(v, 'hole_sketch'), lambda: comp.xYConstructionPlane, circle(E(v, 'pitch / 2'), E(v, v['hole_y']), E(v, 'hole_d')), **kw(v, 'hole_sketch'))

    def hole_cut(b, v, S):
        alt = v['alt'].get('hole_cut')
        participants = (lambda: [b.body('base', 0)]) if alt == 'participants' else (lambda: [b.body('base')])
        profile = (lambda s: s.profiles.item(0)) if alt == 'profile' else None
        b.extrude('hole_cut', label(v, 'hole_cut'), S['hole_sketch'], v['hole_op'], distance=E(v, 'base_h'), participants=participants, profile=profile, **kw(v, 'hole_cut'))

    def hole_pattern(b, v, S):
        comp = S['comp']
        alt = v['alt'].get('hole_pattern')
        if alt == 'with_rounds':  # L3: the rounds go in the pattern with the cut
            bodies = lambda: [b.known['hole_cut'], b.known['hole_rounds']]
        else:
            bodies = (lambda: list([b.known['hole_cut']])) if alt == 'bodies' else (lambda: [b.known['hole_cut']])
        n1, d1, n2, d2 = (E(v, x) for x in v['pattern'])
        b.rect_pattern('hole_pattern', label(v, 'hole_pattern'), bodies, comp.xConstructionAxis, n1, d1, comp.yConstructionAxis, n2, d2, adjust=v['pattern_adjust'], **kw(v, 'hole_pattern'))

    def post_sketch(b, v, S):
        comp = S['comp']
        plane = (lambda: comp.xYConstructionPlane) if v['alt'].get('post_sketch') == 'on_xy' else (lambda: b.known['top_plane'])
        S['post_sketch'] = b.sketch('post_sketch', label(v, 'post_sketch'), plane, v['post_draw'](E(v, 'wall'), E(v, 'wall')), **kw(v, 'post_sketch'))

    def post(b, v, S):
        b.extrude('post', label(v, 'post'), S['post_sketch'], JOIN, distance=E(v, v['post_dist']), participants=lambda: [b.body('base')], **kw(v, 'post'))

    def rib_sketch(b, v, S):
        comp = S['comp']
        S['rib_sketch'] = b.sketch('rib_sketch', label(v, 'rib_sketch'), lambda: comp.xZConstructionPlane, rib_outline(E(v, v['rib_w']), E(v, 'base_h')), **kw(v, 'rib_sketch'))

    def rib(b, v, S):
        b.extrude('rib', label(v, 'rib'), S['rib_sketch'], NEW, symmetric=E(v, v['rib_sym']), body_name='Rib', **kw(v, 'rib'))

    def rib_join(b, v, S):
        alt = v['alt'].get('rib_join')
        target = (lambda: b.body('base', 0)) if alt == 'target' else (lambda: b.body('base'))
        tools = (lambda: [b.body('rib', 0)]) if alt == 'tools' else (lambda: [b.body('rib')])
        b.combine('rib_join', label(v, 'rib_join'), target, tools, v['combine_op'], **kw(v, 'rib_join'))

    def round_(b, v, S):
        alt = v['alt'].get('round')
        r1, r2 = (E(v, r) for r in v['round_r'])
        if alt == 'edges':
            sets = lambda: [(post_top_x(b.body('base')), r1), (corner_edge(b.body('base')), r2)]
        elif alt == 'one':
            sets = lambda: [(post_top(b.body('base')), r1)]
        else:
            sets = lambda: [(post_top(b.body('base')), r1), (corner_edge(b.body('base')), r2)]
        b.fillet('round', label(v, 'round'), sets, **kw(v, 'round'))

    def chamfer(b, v, S):
        d = E(v, v['chamfer_d'])
        if v['alt'].get('chamfer') == 'edges':
            sets = lambda: [(back_bottom_v2(b.body('base')), d)]
        elif v['alt'].get('chamfer') == 'holes':
            sets = lambda: [(first_hole_or_back(b.body('base')), d)]
        else:
            sets = lambda: [(back_bottom(b.body('base')), d)]
        b.chamfer('chamfer', label(v, 'chamfer'), sets, **kw(v, 'chamfer'))

    def mark_sketch(b, v, S):
        b.sketch('mark_sketch', label(v, 'mark_sketch'), lambda: b.known['top_plane'], mark_draw(b, E(v, 'wall')), **kw(v, 'mark_sketch'))

    def block_sketch(b, v, S):
        inner = S['inner']
        S['block_sketch'] = b.sketch('block_sketch', label(v, 'block_sketch'), lambda: inner.xYConstructionPlane, rectangle(E(v, 'base_d / 3'), E(v, 'base_d / 3')), **kw(v, 'block_sketch'))

    def block(b, v, S):
        b.extrude('block', label(v, 'block'), S['block_sketch'], NEW, distance=E(v, 'base_h'), body_name='Block', **kw(v, 'block'))

    def block_move(b, v, S):
        bodies = (lambda: [b.body('block', 0)]) if v['alt'].get('block_move') == 'bodies' else (lambda: [b.body('block')])
        x, y, z = (E(v, e) for e in v['move'])
        b.move('block_move', label(v, 'block_move'), bodies, x, y, z, **kw(v, 'block_move'))

    def stock(b, v, S):
        b.base_body('stock', label(v, 'stock'), stock_box, spec=v['spec'].get('stock', ()), body_name='Stock')

    def cap_plane(b, v, S):
        root = b.comp
        make = offset_plane(root, lambda: root.xYConstructionPlane, E(v, v['cap_off']))
        if v['alt'].get('cap_plane') == 'make':
            base = lambda: root.xYConstructionPlane
            make = offset_plane(root, lambda: base(), E(v, v['cap_off']))
        b.plane('cap_plane', label(v, 'cap_plane'), make, **kw(v, 'cap_plane'))

    def cap_sketch(b, v, S):
        S['cap_sketch'] = b.sketch('cap_sketch', label(v, 'cap_sketch'), lambda: b.known['cap_plane'], rectangle(E(v, 'base_w'), E(v, 'base_d')), **kw(v, 'cap_sketch'))

    def cap(b, v, S):
        b.extrude('cap', label(v, 'cap'), S['cap_sketch'], NEW, distance=E(v, 'wall'), body_name='Cap', **kw(v, 'cap'))

    # Extra steps some scenarios add.
    def mid_plane(b, v, S):
        b.step('mid_plane', label(v, 'mid_plane'), plain_plane(b.comp, '2 mm'), **kw(v, 'mid_plane'))

    def first_plane(b, v, S):
        b.step('first_plane', label(v, 'first_plane'), plain_plane(b.comp, '1 mm'), **kw(v, 'first_plane'))

    def solo_plane(b, v, S):
        b.step('solo_plane', label(v, 'solo_plane'), plain_plane(b.comp, '3 mm'), **kw(v, 'solo_plane'))

    def slab(b, v, S):
        b.base_body('slab', label(v, 'slab'), slab_box, spec=v['spec'].get('slab', ()), body_name='Slab')

    def slab_cut(b, v, S):
        if v['alt'].get('slab_cut') == 'base':
            participants = lambda: [b.body('base')]
        else:
            participants = lambda: [b.body('slab')]
        b.extrude('slab_cut', label(v, 'slab_cut'), S['hole_sketch'], CUT, distance=E(v, 'base_h'), participants=participants, **kw(v, 'slab_cut'))

    def rib_peek(b, v, S):
        comp = S['comp']
        def make():  # slow-ok: the step's "make" line covers it
            body = b.body('rib')  # rib_join took it
            pi = comp.constructionPlanes.createInput()
            pi.setByOffset(body.faces.item(0), vi('1 mm'))
            return comp.constructionPlanes.add(pi)
        b.step('rib_peek', label(v, 'rib_peek'), make)

    def hole_rounds(b, v, S):
        base_h = lambda: b.comp.parentDesign.userParameters.itemByName('base_h').value
        b.fillet('hole_rounds', label(v, 'hole_rounds'), lambda: [(hole_tops(b.body('base'), base_h()), '0.5 mm')], **kw(v, 'hole_rounds'))

    def boom(b, v, S):
        def make():
            raise Exception('boom, on purpose')
        b.step('boom', label(v, 'boom'), make)

    def dup(b, v, S):
        b.step('top_plane', 'Top plane again', plain_plane(b.comp, '4 mm'))

    return {k[:-1] if k.endswith('_') else k: f for k, f in locals().items() if callable(f)}


STEPS = step_table()


def run_order(b, v, S, order):
    for item in order:
        if isinstance(item, tuple):
            with b.group(item[1]):
                run_order(b, v, S, item[2])
            continue
        STEPS[item](b, v, S)
        if v['die_at'] == item:
            raise Exception('stopped on purpose after %s' % item)


def describe(b, v):
    for p in v['params']:
        b.param(p['name'], p['expr'], p['unit'], p.get('comment', ''), p.get('favorite', False), was=p.get('was'))
    S = {'comp': b.comp}
    run_order(b, v, S, v['top_first'])
    with b.component('outer', label(v, 'outer')) as comp:
        S['comp'] = comp
        run_order(b, v, S, v['order'])
        if v['with_inner']:
            with b.component('inner', label(v, 'inner')) as inner:
                S['inner'] = inner
                run_order(b, v, S, v['inner_order'])
            if v['inner_copies']:
                n, d = v['inner_copies']
                b.rect_pattern('inner_copies', label(v, 'inner_copies'), lambda: [b.known['inner']], comp.xConstructionAxis, n, d, comp.yConstructionAxis, '1', '1 mm', **kw(v, 'inner_copies'))
    if v['with_cap']:
        S['comp'] = b.comp
        with b.group('Cap'):
            run_order(b, v, S, v['cap_order'])
