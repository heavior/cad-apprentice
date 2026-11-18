# Tries every feature type in cad_apprentice, in a throwaway tab that is closed
# without saving. Run through the UpsertTestRunner add-in:
# {"id": "features", "file": "tests/test_features.py", "args": {}}
# v1 builds everything, v2 changes each step's own values (each should be edited in place, or say why it
# was replaced), v3 is v2 again and should change nothing. Every feature must end healthy, every value
# read back must match the script, and the model checks must hold. Returns "pass" or "fail".
import math, os, traceback
import adsk.core, adsk.fusion
import upsert_harness as H
from cad_apprentice import deferred, fingerprint, helpers

P = adsk.core.Point3D.create
New = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
OPS = {'new': New, 'join': adsk.fusion.FeatureOperations.JoinFeatureOperation,
       'cut': adsk.fusion.FeatureOperations.CutFeatureOperation}
Adjust = adsk.fusion.PatternComputeOptions.AdjustPatternCompute
Identical = adsk.fusion.PatternComputeOptions.IdenticalPatternCompute


def at(s, x, y, z):
    return s.modelToSketchSpace(P(x, y, z))


def rect(a, b):  # two opposite corners, in model space; drawn inside deferred, which tests it
    def draw(s):
        with deferred(s):
            s.sketchCurves.sketchLines.addTwoPointRectangle(at(s, *a), at(s, *b))
    return draw


def circle(x, y, z, r):
    def draw(s):
        s.sketchCurves.sketchCircles.addByCenterRadius(at(s, x, y, z), r)
    return draw


def line(a, b):
    def draw(s):
        s.sketchCurves.sketchLines.addByTwoPoints(at(s, *a), at(s, *b))
    return draw


def points(*pts):
    def draw(s):
        for p in pts:
            s.sketchPoints.add(at(s, *p))
    return draw


def top_face(body):
    return max(body.faces, key=lambda f: f.pointOnFace.z)


def edge_along(body, d):  # a straight edge of body that runs along model x or y
    i = 'xy'.index(d)
    for e in body.edges:
        a, c = e.startVertex.geometry.asArray(), e.endVertex.geometry.asArray()
        if abs(a[i] - c[i]) > 0.1 and all(abs(a[j] - c[j]) < 1e-6 for j in range(3) if j != i):
            return e
    raise Exception('%s has no edge along %s' % (body.name, d))


def describe(b, v):
    comp = b.comp
    xy, xz, yz = comp.xYConstructionPlane, comp.xZConstructionPlane, comp.yZConstructionPlane
    b.param('block_h', '1 cm', 'cm')
    s = b.sketch('block_sk', 'Block sketch', lambda: xy, rect((0, 0, 0), (4, 3, 0)))
    b.extrude('block', 'Block', s, New, distance='block_h', body_name='Block')

    # The edge is passed as it is, so only which edge it is tells v1 from v2. It comes first: an
    # edge is read when the script runs, so no step before it may roll the timeline back on a rerun.
    b.extrude('rp2_src', 'Pattern block 2', b.sketch('rp2_src_sk', 'Pattern block 2 sketch', lambda: xy, rect((30, 5, 0), (30.5, 5.5, 0))),
              New, distance='0.5 cm', body_name='Pattern block 2')
    b.rect_pattern('rp2', 'Rect pattern edge', lambda: [b.body('rp2_src')], edge_along(b.body('rp2_src'), v['rp2_dir']), '3', '1 cm',
                   comp.zConstructionAxis, '1', '1 cm', uses=['rp2_src'])

    top = b.offset_plane('top', 'Block top', xy, v['top'], along=2)
    mid = b.mid_plane('mid', 'Block middle', xy, lambda: b.known['top'], uses=['top'])
    z_axis = b.axis('z_axis', 'Z axis', 'two_planes', yz, xz)
    b.angled_plane('tilt', 'Tilted plane', z_axis, v['tilt'], xz, uses=['z_axis'])

    # The ring turns about the Z axis, then about a second axis at x = 4 (an axis that changes).
    b.sketch('ring_ax_sk', 'Ring axis line', lambda: xz, line((4, 0, 0), (4, 0, 1)))
    b.axis('ring_ax', 'Ring second axis', 'line', lambda: b.known['ring_ax_sk'].sketchCurves.item(0), uses=['ring_ax_sk'])
    ring_axis = v['ring_axis']
    ring = b.sketch('ring_sk', 'Ring section', lambda: xz, rect((6, 0, 0), (7, 0, 0.5)))
    b.revolve('ring', 'Ring', ring, lambda: b.known[ring_axis], New, angle=v['ring'], body_name='Ring', uses=['z_axis', 'ring_ax'])

    path = b.sketch('path_sk', 'Rod path', lambda: xz, line((0, 0, 3), (3, 0, 3)))
    b.pipe('rod', 'Rod', lambda: [path.sketchCurves.item(0)], v['rod'], New, body_name='Rod', uses=['path_sk'])
    # The swept bar follows the rod's path, then a path of its own that climbs (a path that changes).
    b.sketch('path2_sk', 'Climbing path', lambda: xz, line((0, 0, 3), (3, 0, 4)))
    sweep_path = v['sweep_path']
    prof = b.sketch('sweep_sk', 'Sweep section', lambda: yz, circle(0, 0, 3, 0.3))
    b.sweep('sweep', 'Swept bar', prof, lambda: [b.known[sweep_path].sketchCurves.item(0)], New, body_name=v['sweep_name'],
            uses=['path_sk', 'path2_sk'])

    lo = b.offset_plane('loft_lo', 'Loft low', xy, '4 cm')
    hi = b.offset_plane('loft_hi', 'Loft high', xy, v['loft'])
    a = b.sketch('loft_a', 'Loft base', lambda: b.known['loft_lo'], circle(8, 0, 4, 1), uses=['loft_lo'])
    c = b.sketch('loft_b', 'Loft top', lambda: b.known['loft_hi'], circle(8, 0, 6, 0.5), uses=['loft_hi'])
    b.loft('loft', 'Loft', lambda: [a.profiles.item(0), c.profiles.item(0)], New, body_name='Loft', uses=['loft_a', 'loft_b'])

    hs = b.sketch('hole_sk', 'Hole spots', lambda: b.known['top'], points((1, 1, 1), (3, 2, 1)), uses=['top'])
    b.hole('holes', 'Screw holes', lambda: [p for p in hs.sketchPoints if not p.isReference][:2], v['hole'], depth='0.6 cm',
           kind='counterbore', head=(v['head'], '0.2 cm'), uses=['hole_sk', 'block'])
    hs2 = b.sketch('hole_sk2', 'More hole spots', lambda: b.known['top'], points((1, 2.2, 1), (3, 0.8, 1)), uses=['top'])
    spots2 = lambda: list(hs2.sketchPoints)[1:]  # item 0 is the sketch's own origin point
    simple, sink = v['simple'], v['sink']
    b.hole('hole_simple', 'Simple hole', lambda: spots2()[:1], simple[0], depth=simple[1], uses=['hole_sk2', 'block'])
    b.hole('hole_sink', 'Countersink hole', lambda: spots2()[1:2], sink[0], kind='countersink', head=sink[1:],
           uses=['hole_sk2', 'block'])

    b.mirror('rod_mirror', 'Rod mirrored', lambda: [b.body('rod')], yz, body_name='Rod mirrored', uses=['rod'])

    peg = b.sketch('peg_sk', 'Peg sketch', lambda: xy, circle(5, 0, 0, 0.3))
    b.extrude('peg', 'Peg', peg, New, distance='2 cm', body_name='Peg')
    b.circular_pattern('pegs', 'Pegs', lambda: [b.body('peg')], lambda: b.known['z_axis'], v['pegs'], uses=['peg', 'z_axis'])

    bead = b.sketch('bead_sk', 'Bead sketch', lambda: xz, rect((-0.2, 0, 2.8), (0.2, 0, 3.2)))
    b.extrude('bead', 'Bead', bead, New, symmetric='0.4 cm', body_name='Bead')
    b.path_pattern('beads', 'Beads', lambda: [b.body('bead')], lambda: [path.sketchCurves.item(0)], v['beads'], '0.8 cm',
                   uses=['bead', 'path_sk'])

    slab = b.sketch('slab_sk', 'Slab sketch', lambda: xy, rect((-2, -6, 0), (2, -4, 0)))
    b.extrude('slab', 'Slab', slab, New, distance='1 cm', body_name='Slab')
    b.split_body('slab_split', 'Slab split', lambda: b.body('slab'), {'yz': yz, 'mid': lambda: b.known['mid']}[v['split']], uses=['slab', 'mid'])

    # The other ways to make an axis or a point: built once, checked healthy.
    ref = b.sketch('ref_sk', 'Reference lines', lambda: xy, lambda s: [line((12, 0, 0), (14, 2, 0))(s), line((12, 2, 0), (14, 0, 0))(s),
                                                                     circle(13, 5, 0, 0.5)(s), points((12, 8, 0), (14, 9, 0))(s)])
    lines = lambda: [c for c in b.known['ref_sk'].sketchCurves.sketchLines]
    dots = lambda: [p for p in b.known['ref_sk'].sketchPoints if not p.isReference and not p.connectedEntities]
    b.axis('ax_line', 'Axis on a line', 'line', lambda: lines()[0], uses=['ref_sk'])
    b.axis('ax_points', 'Axis through two points', 'two_points', lambda: dots()[0], lambda: dots()[1], uses=['ref_sk'])
    b.axis('ax_normal', 'Axis square to the block top', 'normal', lambda: top_face(b.body('block')),
           lambda: min(b.body('block').vertices, key=lambda x: x.geometry.distanceTo(P(4, 3, 0))), uses=['block'])
    b.point('pt_cross', 'Where the lines cross', 'two_lines', lambda: lines()[0], lambda: lines()[1], uses=['ref_sk'])
    b.point('pt_center', 'Circle centre', 'center', lambda: b.known['ref_sk'].sketchCurves.sketchCircles.item(0), uses=['ref_sk'])

    box = b.sketch('box_sk', 'Box sketch', lambda: xy, rect((-4, 4, 0), (-1, 7, 0)))
    b.extrude('box', 'Box', box, New, distance='2 cm', body_name='Box')
    side = v['shell_side']
    b.shell('box_shell', 'Box shell', lambda: [top_face(b.body('box'))] + ([max(b.body('box').faces, key=lambda f: f.pointOnFace.x)] if side else []),
            v['wall'], uses=['box'])

    cube = b.sketch('cube_sk', 'Cube sketch', lambda: xy, rect((-7, 0, 0), (-6, 1, 0)))
    b.extrude('cube', 'Cube', cube, New, distance='1 cm', body_name='Cube')
    corner = b.sketch('corner_sk', 'Cube corner', lambda: xy, points((-7, 0, 0)))
    b.point('corner', 'Cube corner point', 'point', lambda: [p for p in corner.sketchPoints if not p.isReference][0], uses=['corner_sk'])
    b.scale('cube_scale', 'Cube scaled', lambda: [b.body('cube')], lambda: b.known['corner'], v['grow'], uses=['cube', 'corner'])

    # A bar of its own for each edge treatment, so each one's top edges change only with it.
    def bar(k, x):
        sk = b.sketch(k + '_sk', k + ' sketch', lambda: xy, rect((x, -10, 0), (x + 2, -8, 0)))
        b.extrude(k, k, sk, New, distance='1 cm', body_name=k)
        return lambda: helpers.face_edges(top_face(b.body(k)), True)

    # Plain values, not v[...]: a step's fingerprint reads captured strings and tuples, never a dict.
    cham, cham2, cham_a = v['cham'], v['cham2'], v['cham_a']
    eq_edges = bar('cham_eq', 0)
    b.chamfer('cham_eq_c', 'Chamfer equal', lambda: [(eq_edges(), cham)], uses=['cham_eq'])
    two_edges = bar('cham_two', 3)
    b.chamfer('cham_two_c', 'Chamfer two distances', lambda: [(two_edges(), 'two') + cham2], uses=['cham_two'])
    ang_edges = bar('cham_ang', 6)
    b.chamfer('cham_ang_c', 'Chamfer distance and angle', lambda: [(ang_edges(), 'angle') + cham_a], uses=['cham_ang'])

    # Fillets of each kind. A variable radius takes one edge, the bar's back top edge.
    def back_edge(k):
        c = adsk.core.ObjectCollection.create()
        c.add(max(top_face(b.body(k)).edges, key=lambda ed: ed.pointOnEdge.y))
        return c

    round_r, chord, var = v['round'], v['chord'], v['var']
    round_edges = bar('fil_r', 9)
    b.fillet('fil_r_f', 'Fillet constant', lambda: [(round_edges(), round_r)], uses=['fil_r'])
    chord_edges = bar('fil_chord', 12)
    b.fillet('fil_chord_f', 'Fillet chord length', lambda: [(chord_edges(), 'chord', chord)], uses=['fil_chord'])
    bar('fil_var', 15)
    b.fillet('fil_var_f', 'Fillet variable radius', lambda: [(back_edge('fil_var'), 'variable') + var], uses=['fil_var'])

    thin = v['thin']
    tube = b.sketch('tube_sk', 'Tube sketch', lambda: xy, rect((18, -10, 0), (20, -8, 0)))
    b.extrude('tube', 'Thin tube', tube, New, distance='1 cm', thin=thin, body_name='Thin tube')

    # One row per value an edit used to log as "updated" and leave as it was. Each one changes from
    # v1 to v2, and model_checks() reads the model to see that it really did.
    block = lambda k, name, a, c, h: b.extrude(k, name, b.sketch(k + '_sk', name + ' sketch', lambda: xy, rect(a, c)), New,
                                               distance=h, body_name=name)
    block('cmb_a', 'Combine target', (22, 4, 0), (25, 7, 0), '1 cm')
    b.extrude('cmb_b', 'Combine tool', b.sketch('cmb_b_sk', 'Combine tool sketch', lambda: xy, circle(25, 7, 0, 1)), New,
              distance='2 cm', body_name='Combine tool')
    b.combine('cmb', 'Combine', lambda: b.body('cmb_a'), lambda: [b.body('cmb_b')], OPS[v['cmb_op']], body_name=v['cmb_name'],
              uses=['cmb_a', 'cmb_b'])

    b.sketch('p2_path', 'Hollow pipe path', lambda: xz, line((22, 0, 5), (26, 0, 5)))
    b.pipe('p2', 'Pipe hollow', lambda: [b.known['p2_path'].sketchCurves.item(0)], '0.6 cm', New, hollow=v['p2_hollow'],
           body_name=v['p2_name'], uses=['p2_path'])
    block('pbar', 'Pipe bar', (22, -1, 0), (26, 1, 0), '1 cm')
    b.sketch('p3_path', 'Cut pipe path', lambda: xz, line((22, 0, 0.5), (26, 0, 0.5)))
    b.pipe('p3', 'Pipe cut', lambda: [b.known['p3_path'].sketchCurves.item(0)], '0.4 cm', OPS[v['p3_op']], uses=['p3_path', 'pbar'])

    pp_item, pp_path = v['pp_item'], v['pp_path']
    b.path_pattern('beads2', 'Beads 2', lambda: [b.body(pp_item)], lambda: [b.known[pp_path].sketchCurves.item(0)], '3', '0.8 cm',
                   uses=['bead', 'peg', 'path_sk', 'path2_sk'])

    block('cube2', 'Cube 2', (-7, -3, 0), (-6, -2, 0), '1 cm')
    block('cube3', 'Cube 3', (-7, -6, 0), (-6, -5, 0), '1 cm')
    b.sketch('sc_pts', 'Scale corners', lambda: xy, points((-7, -3, 0), (-7, -6, 0)))
    sc_body, sc_pt = v['sc_body'], v['sc_pt']
    b.scale('scale2', 'Scaled 2', lambda: [b.body(sc_body)], lambda: list(b.known['sc_pts'].sketchPoints)[1 + sc_pt],
            '2', uses=['cube2', 'cube3', 'sc_pts'])

    block('sp_a', 'Split A', (-1, -14, 0), (1, -12, 0), '1 cm')
    block('sp_b', 'Split B', (-1, -17, 0), (1, -15, 0), '1 cm')
    sp = v['sp_body']
    b.split_body('split2', 'Split 2', lambda: b.body(sp), yz, uses=['sp_a', 'sp_b'])

    block('mir_src', 'Mirror source', (0, -20, 0), (1, -19, 0), '1 cm')
    b.mirror('mir2', 'Mirror 2', lambda: [b.body('mir_src')], yz, combine=v['mir_join'], body_name=v['mir_name'], uses=['mir_src'])

    b.offset_plane('pg2_pl', 'Peg 2 plane', xy, '12 cm')
    b.extrude('peg2', 'Peg 2', b.sketch('peg2_sk', 'Peg 2 sketch', lambda: b.known['pg2_pl'], circle(6, 0, 12, 0.3), uses=['pg2_pl']),
              New, distance='1 cm', body_name='Peg 2')
    pg2_axis = v['pg2_axis']
    b.circular_pattern('pegs2', 'Pegs 2', lambda: [b.body('peg2')], lambda: b.known[pg2_axis], '2', adjust=v['pg2_adjust'],
                       uses=['peg2', 'z_axis', 'ring_ax'])

    block('rp_src', 'Pattern block', (30, 0, 0), (30.5, 0.5, 0), '0.5 cm')
    b.rect_pattern('rp', 'Rect pattern adjust', lambda: [b.body('rp_src')], comp.xConstructionAxis, '2', '1 cm',
                   comp.yConstructionAxis, '1', '1 cm', adjust=v['rp_adjust'], uses=['rp_src'])

    # Patterns of a feature, not bodies (fusion/rules.md rule 32): a row of holes with a compute option,
    # and a symmetric circular row, whose angle covers both sides.
    block('cp', 'Compute plate', (40, 0, 0), (46, 2, 0), '0.5 cm')
    b.extrude('cp_hole', 'Compute hole', b.sketch('cp_hole_sk', 'Compute hole sketch', lambda: xy, circle(41, 1, 0, 0.2)),
              OPS['cut'], distance='0.5 cm', participants=lambda: [b.body('cp')], uses=['cp'])
    b.rect_pattern('cp_row', 'Compute row', lambda: [b.known['cp_hole']], comp.xConstructionAxis, '3', '1 cm',
                   comp.yConstructionAxis, '1', '1 cm', compute=v['cp_compute'], uses=['cp_hole'])
    block('cs', 'Symmetric plate', (47, -3, 0), (53, 3, 0), '0.5 cm')
    b.extrude('cs_hole', 'Symmetric hole', b.sketch('cs_hole_sk', 'Symmetric hole sketch', lambda: xy, circle(52.5, 0, 0, 0.2)),
              OPS['cut'], distance='0.5 cm', participants=lambda: [b.body('cs')], uses=['cs'])
    b.sketch('cs_ax_sk', 'Symmetric row axis line', lambda: xz, line((50, 0, 0), (50, 0, 1)))
    b.axis('cs_ax', 'Symmetric row axis', 'line', lambda: b.known['cs_ax_sk'].sketchCurves.item(0), uses=['cs_ax_sk'])
    b.circular_pattern('cs_row', 'Symmetric row', lambda: [b.known['cs_hole']], lambda: b.known['cs_ax'], v['cs_n'], '90 deg',
                       symmetric=True, compute='identical', uses=['cs_hole', 'cs_ax'])

    block('hp', 'Hole plate', (22, -8, 0), (26, -6, 0), '2 cm')
    b.offset_plane('hp_top', 'Hole plate top', xy, '2 cm')
    b.sketch('hp_pts', 'Hole plate spot', lambda: b.known['hp_top'], points((24, -7, 2)), uses=['hp_top'])
    h3 = v['h3']
    b.hole('hole3', 'Hole 3', lambda: list(b.known['hp_pts'].sketchPoints)[1:2], '0.3 cm', depth=h3[1],
           kind=h3[0], head=('0.6 cm', '0.3 cm') if h3[0] == 'counterbore' else None, uses=['hp_pts', 'hp'])

    block('pa', 'Part A', (22, -11, 0), (24, -10, 0), '1 cm')
    block('pb', 'Part B', (24, -11, 0), (26, -10, 0), '1 cm')
    only_a = (lambda: [b.body('pa')]) if v['only_a'] else None
    b.extrude('pcut', 'Participants cut', b.sketch('pcut_sk', 'Participants cut sketch', lambda: xy, rect((23, -10.8, 0), (25, -10.2, 0))),
              OPS['cut'], distance='1 cm', participants=only_a, uses=['pa', 'pb'])

    b.extrude('tap', 'Taper', b.sketch('tap_sk', 'Taper sketch', lambda: xy, rect((22, -14, 0), (24, -12, 0))), New,
              symmetric=v['tap'], taper='5 deg', body_name='Taper')

    block('tb', 'Turned block', (30, 10, 0), (31, 12, 0), '1 cm')
    b.turn('turn', 'Turn', lambda: [b.body('tb')], b.known['z_axis'], v['turn'], uses=['tb', 'z_axis'])

    copy_src = v['copy_src']
    b.copy('copy', 'Copy', lambda: b.body(copy_src), body_name='Copy', uses=['peg', 'bead'])

    helper = b.sketch('helper_sk', 'Helper sketch', lambda: xy, rect((10, 10, 0), (11, 11, 0)))
    b.extrude('helper', 'Helper', helper, New, distance='1 cm', body_name='Helper')
    b.remove('helper_gone', 'Helper removed', lambda: b.body('helper'), uses=['helper'])


V1 = dict(top='block_h', tilt='30 deg', ring='270 deg', rod='0.4 cm', loft='6 cm', hole='0.3 cm', head='0.5 cm',
          pegs='4', beads='3', wall='0.2 cm', grow='1.5', split='yz',
          cham='1 mm', cham2=('1 mm', '2 mm'), cham_a=('1 mm', '30 deg'),
          round='1 mm', chord='1 mm', var=('1 mm', '3 mm', (('0.5', '2 mm'),)), thin=('1 mm', 'center'),
          ring_axis='z_axis', sweep_path='path_sk', simple=('0.2 cm', '0.5 cm'), sink=('0.2 cm', '0.6 cm', '90 deg'),
          cmb_op='join', cmb_name='Combined', p2_hollow=None, p2_name='Pipe', p3_op='new', pp_item='bead', pp_path='path_sk',
          sc_body='cube2', sc_pt=0, sp_body='sp_a', mir_join=False, mir_name='Mirror copy', pg2_axis='z_axis', pg2_adjust=True,
          rp_adjust=True, rp2_dir='x', h3=('counterbore', '0.5 cm'), only_a=True, tap='1 cm', turn='30 deg', copy_src='peg',
          shell_side=False, sweep_name='Swept bar', cp_compute='identical', cs_n='3')
V2 = dict(top='block_h * 1', tilt='45 deg', ring='180 deg', rod='0.5 cm', loft='7 cm', hole='0.25 cm', head='0.6 cm',
          pegs='6', beads='4', wall='0.3 cm', grow='2', split='mid',
          cham='1.5 mm', cham2=('1.5 mm', '0.5 mm'), cham_a=('2 mm', '45 deg'),
          round='2 mm', chord='2 mm', var=('2 mm', '4 mm', (('0.3', '1 mm'), ('0.7', '3 mm'))), thin=('2 mm', 'side2'),
          ring_axis='ring_ax', sweep_path='path2_sk', simple=('0.25 cm', '0.7 cm'), sink=('0.25 cm', '0.7 cm', '82 deg'),
          cmb_op='cut', cmb_name='Combined 2', p2_hollow='0.1 cm', p2_name='Pipe 2', p3_op='cut', pp_item='peg', pp_path='path2_sk',
          sc_body='cube3', sc_pt=1, sp_body='sp_b', mir_join=True, mir_name='Mirror joined', pg2_axis='ring_ax', pg2_adjust=False,
          rp_adjust=False, rp2_dir='y', h3=('simple', None), only_a=False, tap='1.2 cm', turn='60 deg', copy_src='bead',
          shell_side=True, sweep_name='Swept bar 2', cp_compute='adjust', cs_n='5')

# What v2 should touch: every step whose own values changed, and the ones built on them. Each is
# "updated" (edited in place); the ones in MAY_REPLACE may be replaced instead, if the log says why.
EXPECT_V2 = dict.fromkeys(['Block top', 'Block middle', 'Tilted plane', 'Ring', 'Rod', 'Swept bar', 'Loft high', 'Loft top', 'Loft',
                           'Hole spots', 'Screw holes', 'More hole spots', 'Simple hole', 'Countersink hole', 'Rod mirrored', 'Pegs',
                           'Beads', 'Slab split', 'Box shell', 'Cube scaled', 'Chamfer equal', 'Chamfer two distances',
                           'Chamfer distance and angle', 'Fillet constant', 'Fillet chord length', 'Fillet variable radius',
                           'Thin tube', 'Combine', 'Pipe hollow', 'Pipe cut', 'Beads 2', 'Scaled 2', 'Split 2', 'Mirror 2', 'Pegs 2',
                           'Rect pattern adjust', 'Rect pattern edge', 'Hole 3', 'Participants cut', 'Taper', 'Turn',
                           'Symmetric row'], 'updated')
EXPECT_V2['Copy'] = 'replaced'  # a copy has nothing to edit
EXPECT_V2['Compute row'] = 'replaced'  # a new compute option makes the pattern again
MAY_REPLACE = ('Combine', 'Pipe hollow', 'Pipe cut', 'Beads 2', 'Scaled 2', 'Split 2', 'Mirror 2', 'Pegs 2', 'Rect pattern adjust',
               'Rect pattern edge', 'Hole 3', 'Participants cut', 'Copy', 'Compute row')


# What each step's reader should give back: the script's values.
def expected(v):
    cm = lambda *ks: dict.fromkeys(ks, '1 cm')
    out = cm('slab', 'cube', 'cham_eq', 'cham_two', 'cham_ang', 'fil_r', 'fil_chord', 'fil_var', 'helper', 'cmb_a', 'pbar', 'cube2',
             'cube3', 'sp_a', 'sp_b', 'mir_src', 'peg2', 'pa', 'pb', 'pcut', 'tb')
    out.update(block='block_h', top=v['top'], tilt=v['tilt'], ring=v['ring'], rod=v['rod'], loft_lo='4 cm', loft_hi=v['loft'],
               holes=v['hole'], hole_simple=v['simple'][0], hole_sink=v['sink'][0], peg='2 cm', pegs=v['pegs'] + ';360 deg',
               bead='0.4 cm', beads=v['beads'] + ';0.8 cm', box='2 cm', box_shell=v['wall'], cube_scale=v['grow'],
               cham_eq_c=v['cham'], cham_two_c=','.join(v['cham2']), cham_ang_c=','.join(v['cham_a']), fil_r_f=v['round'],
               fil_chord_f=v['chord'], fil_var_f=','.join(v['var'][:2] + tuple('%s@%s' % (r, at) for at, r in v['var'][2])),
               tube='1 cm,%s,%s' % v['thin'], cmb_b='2 cm', p2='0.6 cm', p3='0.4 cm', beads2='3;0.8 cm', scale2='2',
               pegs2='2;360 deg', rp_src='0.5 cm', rp2_src='0.5 cm', rp='2;1 cm;1;1 cm', rp2='3;1 cm;1;1 cm', hp='2 cm',
               hole3='0.3 cm', tap=v['tap'], turn=v['turn'], cp_row='3;1 cm;1;1 cm', cs_row=v['cs_n'] + ';90 deg')
    return out


same_value = H.same_value


def bodies_in(des, x0, x1, y0, y1):
    out = []
    for x in des.rootComponent.bRepBodies:
        bb = x.boundingBox
        cx, cy = (bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2
        if x0 < cx < x1 and y0 < cy < y1:
            out.append(x)
    return out


def named(des, name):
    return [x for x in des.rootComponent.bRepBodies if x.name == name]


def span(bodies, i):
    lo = min(x.boundingBox.minPoint.asArray()[i] for x in bodies)
    return max(x.boundingBox.maxPoint.asArray()[i] for x in bodies) - lo


# A pattern's or shell's inputs can only be read with the marker before it ("Didn't roll editing feature
# back" at the end), so read() runs there and the marker goes back to the end.
def rolled(des, f, read):
    try:
        f.timelineObject.rollTo(True)
        return read()
    except Exception as err:
        return 'unknown (%s)' % err
    finally:
        des.timeline.moveToEnd()


# What the model must look like after a build with v: the value each F1 row changes, read off the model.
def model_checks(bl, des, v, label, t):
    k = bl.known
    um = des.unitsManager
    check = lambda ok, what: t.expect(ok, '%s: %s' % (label, what))
    f = k['cmb']
    check(f.operation == OPS[v['cmb_op']], 'Combine operation is %s, not %s' % (f.operation, v['cmb_op']))
    check(bl.body('cmb').name == v['cmb_name'], 'Combine body is named %s, not %s' % (bl.body('cmb').name, v['cmb_name']))
    vol = bl.body('cmb').volume
    check(vol > 9 if v['cmb_op'] == 'join' else vol < 9, 'Combine volume %.3f does not fit a %s' % (vol, v['cmb_op']))
    f = k['p2']
    check(f.isHollow == bool(v['p2_hollow']), 'Pipe hollow: isHollow is %s' % f.isHollow)
    check(bl.body('p2').name == v['p2_name'], 'Pipe hollow body is named %s, not %s' % (bl.body('p2').name, v['p2_name']))
    vol = bl.body('pbar').volume
    check(abs(vol - 8) < 1e-3 if v['p3_op'] == 'new' else vol < 7.9, 'Pipe bar volume %.3f does not fit a %s pipe' % (vol, v['p3_op']))
    f = k['beads2']
    names = rolled(des, f, lambda: sorted(f.inputEntities.item(i).name for i in range(f.inputEntities.count)))
    check(names == [bl.body(v['pp_item']).name], 'Beads 2 patterns %s, not %s' % (names, bl.body(v['pp_item']).name))
    on = rolled(des, f, lambda: f.path.item(0).entity.parentSketch.name)
    check(on == k[v['pp_path']].name, 'Beads 2 runs along %s, not %s' % (on, k[v['pp_path']].name))
    for key, other in (('cube2', 'cube3'), ('cube3', 'cube2')):
        size = span([bl.body(key)], 0)
        check(abs(size - (2 if key == v['sc_body'] else 1)) < 1e-3, '%s is %.3f across' % (bl.body(key).name, size))
    low_y = bl.body(v['sc_body']).boundingBox.minPoint.y
    check(abs(low_y - (-3, -6)[v['sc_pt']]) < 1e-3, 'Scaled 2 grew from y %.3f, not its own corner' % low_y)
    for key, y0, y1 in (('sp_a', -14, -12), ('sp_b', -17, -15)):
        n = len(bodies_in(des, -2, 2, y0, y1))
        check(n == (2 if key == v['sp_body'] else 1), '%d bodies where %s is' % (n, bl.body(key).name if n == 1 else key))
    n = len(bodies_in(des, -2, 2, -20, -19))
    check(n == (1 if v['mir_join'] else 2), 'Mirror 2 left %d bodies' % n)
    check(len(named(des, v['mir_name'])) == 1, 'no body named %s' % v['mir_name'])
    f = k['pegs2']
    lo = min(x.boundingBox.minPoint.x for x in list(f.bodies) + [bl.body('peg2')])
    check(lo < -5 if v['pg2_axis'] == 'z_axis' else lo > 1, 'Pegs 2 reaches x %.2f, wrong for the %s' % (lo, v['pg2_axis']))
    # Without adjust, Fusion's own default is Adjust too, so only adjust=True is checked.
    check(f.patternComputeOption == Adjust or not v['pg2_adjust'], 'Pegs 2 compute option is %s' % f.patternComputeOption)
    f = k['rp']
    check(f.patternComputeOption == Adjust or not v['rp_adjust'], 'Rect pattern adjust: compute option is %s' % f.patternComputeOption)
    f = k['rp2']
    got = list(f.bodies) + [bl.body('rp2_src')]
    along, across = (0, 1) if v['rp2_dir'] == 'x' else (1, 0)
    check(span(got, along) > 2 and span(got, across) < 1, 'Rect pattern edge spreads %.2f along x and %.2f along y, not along %s'
          % (span(got, 0), span(got, 1), v['rp2_dir']))
    f = k['hole3']
    kind = {'simple': adsk.fusion.HoleTypes.SimpleHoleType, 'counterbore': adsk.fusion.HoleTypes.CounterboreHoleType}[v['h3'][0]]
    check(f.holeType == kind, 'Hole 3 type is %s, not %s' % (f.holeType, v['h3'][0]))
    vol = bl.body('hp').volume
    if v['h3'][1] is None:
        check(abs(vol - (16 - math.pi * 0.15 ** 2 * 2)) < 1e-3, 'Hole 3 plate volume %.4f: the hole does not go through' % vol)
    vol = bl.body('pb').volume
    check(abs(vol - (2 if v['only_a'] else 1.4)) < 1e-3, 'Part B volume %.3f: the cut %s it' % (vol, 'reached' if v['only_a'] else 'missed'))
    d = um.evaluateExpression(v['tap'], 'cm')
    vol = bl.body('tap').volume
    check(abs(vol - 4 * d) > 1e-3, 'Taper volume %.4f is a straight block %s thick: the taper is missing' % (vol, v['tap']))
    bb = bl.body('tb').boundingBox
    angle = math.degrees(math.atan2((bb.minPoint.y + bb.maxPoint.y) / 2, (bb.minPoint.x + bb.maxPoint.x) / 2))
    want = math.degrees(math.atan2(11, 30.5)) + um.evaluateExpression(v['turn'], 'deg') * 180 / math.pi
    check(abs(angle - want) < 0.01, 'Turned block sits at %.2f deg, not %.2f' % (angle, want))
    copies = named(des, 'Copy')
    check(len(copies) == 1 and abs(copies[0].volume - bl.body(v['copy_src']).volume) < 1e-4,
          'Copy is not a copy of %s' % bl.body(v['copy_src']).name)
    f = k['box_shell']
    n = rolled(des, f, lambda: f.inputEntities.count)
    check(n == (2 if v['shell_side'] else 1), 'Box shell leaves %s faces open' % n)
    check(bl.body('sweep').name == v['sweep_name'], 'Swept bar body is named %s' % bl.body('sweep').name)
    f = k['cp_row']
    want = {'identical': Identical, 'adjust': Adjust}[v['cp_compute']]
    check(f.patternComputeOption == want, 'Compute row compute option is %s, not %s' % (f.patternComputeOption, v['cp_compute']))
    hole = math.pi * 0.2 ** 2 * 0.5
    vol = bl.body('cp').volume
    check(abs(vol - (6 - 3 * hole)) < 1e-4, 'Compute plate volume %.4f: not 3 holes through it' % vol)
    f = k['cs_row']
    check(f.isSymmetric and f.patternComputeOption == Identical, 'Symmetric row: symmetric %s, compute option %s'
          % (f.isSymmetric, f.patternComputeOption))
    plate = bl.body('cs')
    n = int(v['cs_n'])
    check(abs(plate.volume - (18 - n * hole)) < 1e-4, 'Symmetric plate volume %.4f: not %d holes through it' % (plate.volume, n))
    y = plate.physicalProperties.centerOfMass.y
    check(abs(y) < 1e-4, 'Symmetric plate balances at y %.4f, not 0: the holes are not spread to both sides' % y)


health = H.timeline_health  # test_edit_in_place imports it from here


def uses_p3():
    return p3(1, 2)


def helper_prints():
    # A function that reads a helpers.py function by name: its fingerprint must change with that helper.
    g = globals()
    g['p3'] = helpers.p3
    first = fingerprint(uses_p3)
    g['p3'] = helpers.mm
    second = fingerprint(uses_p3)
    g['p3'] = helpers.p3
    return {'changes_with_helper': first != second, 'stable': first == fingerprint(uses_p3)}


def main(args):
    t = H.Verdict()
    hp = helper_prints()
    t.expect(hp['changes_with_helper'] and hp['stable'], 'a fingerprint does not follow a helpers.py function: %s' % hp)
    out = {}
    doc, des = H.new_tab()
    try:
        for label, v, want in (('v1', V1, None), ('v2', V2, EXPECT_V2), ('v3', V2, None)):
            r = H.build(doc, des, describe, v, os.path.join(OUT_DIR, label + '.log'))
            out[label] = {'counts': r.get('counts'), 'touched': r.get('touched'),
                          'log': [l for l in r['log'] if 'could not edit' in l or 'BROKEN' in l or 'replac' in l]}
            if not t.run(label, r, des, first=label == 'v1', want=want, may_replace=MAY_REPLACE):
                out[label]['error'] = r.get('trace')
                break
            bl = r['builder']
            got = {k: m[6](bl.known[k]) for k, m in bl.made.items() if m[6] and bl.known[k].isValid}
            for k, w in sorted(expected(v).items()):
                t.expect(k in got and same_value(des.unitsManager, got[k], w), '%s: %s reads %s, not %s' % (label, k, got.get(k), w))
            try:
                model_checks(bl, des, v, label, t)
            except Exception as err:
                line = [f.lineno for f in traceback.extract_tb(err.__traceback__) if f.filename.endswith('test_features.py')][-1]
                t.fails.append('%s: the model checks stopped at line %d: %s' % (label, line, err))
        out['bodies'] = sorted(x.name for x in des.rootComponent.bRepBodies)
    finally:
        H.close_tab(doc)
    return t.result(**out)
