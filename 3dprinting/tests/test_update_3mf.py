"""Group U (U1-U17) of 3dprinting/3mf-test-scenarios.md: update_3mf.py swaps new meshes
into a project the person has tuned.

Runs alone: update_3mf.py refuses while any Bambu Studio runs, and the B and P tests start its
command line (§ 1). Every update runs on a copy in run/.

The base project is built by build_3mf.py from four test STLs, then "tuned" the way a person would in
Bambu Studio, by editing the files in the zip:
- a global setting: wall_loops 2 -> 3
- alpha: infill 40 % on the object, and a modifier inside it (a 10 mm box, infill 100 %), stored the
  way Bambu Studio stores modifiers (a type="other" mesh, a component, a modifier_part)
- beta: turned 90 degrees and moved, on filament 2, its plate renamed "beta tuned"
- gamma: a second copy 90 mm to the side (a second object sharing the mesh, the way Bambu Studio
  stores copies), its plate locked
- delta: renamed "delta renamed" in Bambu Studio, packed onto plate 1, its own plate removed
"""
import math, os, re, shutil, subprocess, sys, time, unittest, uuid, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa
import summary as S


def l_long(length):
    """The L-block with its slab made longer in x."""
    return grid_solid([0, 15, length], [0, 10, 30], [0, 10, 25], lambda i, j, k: k == 0 or (i == 0 and j == 0))


def delta_wide(width):
    """The holed overhang with its arm made longer in x."""
    return grid_solid([0, 10, 20, 30, width], [0, 10, 20, 30], [0, 15, 20],
                      lambda i, j, k: (i < 3 and not (i == 1 and j == 1)) or (i == 3 and k == 1 and j == 1))


V1 = {'alpha': box(20, 20, 20), 'beta': l_block(), 'gamma': box(15, 15, 10), 'delta': holed_overhang()}
NAMES = ['alpha', 'beta', 'gamma', 'delta']
MOD_AT = (6, 6, 10)  # the modifier's centre in alpha's own frame (the STL's frame)
# The template prints one object after the other ("by object"), so parts on one plate must stay
# about 70 mm apart (extruder_clearance_max_radius 68) or the plate doesn't slice.
COPY_DX = 90  # gamma's second copy, this far to the side
DELTA_AT = (220, 220)  # delta's centre on plate 1, far from alpha in the middle


def stl_files(d, changes=None, leave_out=(), extra=None):
    """The four STLs (v1 unless changed) plus extra ones, written into d/stl. Returns their paths."""
    shapes = dict(V1)
    shapes.update(changes or {})
    out = []
    for n in NAMES:
        if n not in leave_out:
            out.append(write_stl(os.path.join(d, 'stl', n + '.stl'), shapes[n]))
    for n, tris in (extra or {}).items():
        out.append(write_stl(os.path.join(d, 'stl', n + '.stl'), tris))
    return out


def mesh_xml(tris):
    idx, verts, faces = {}, [], []
    for t in tris:
        f = []
        for p in t:
            if p not in idx:
                idx[p] = len(verts)
                verts.append(p)
            f.append(idx[p])
        faces.append(f)
    return ('<mesh>\n    <vertices>\n' + ''.join('     <vertex x="%.9g" y="%.9g" z="%.9g"/>\n' % p for p in verts)
            + '    </vertices>\n    <triangles>\n' + ''.join('     <triangle v1="%d" v2="%d" v3="%d"/>\n' % tuple(f) for f in faces)
            + '    </triangles>\n   </mesh>')


def fmt(vals):
    return ' '.join('%.9g' % v for v in vals)


def item_tag(model, oid):
    return re.search(r'<item objectid="%s" [^>]*/>' % oid, model).group(0)


def set_item(model, oid, m):
    tag = item_tag(model, oid)
    return model.replace(tag, re.sub(r'transform="[^"]*"', 'transform="%s"' % fmt(m), tag))


def tune(src, dst):
    """Change the project the way a person would in Bambu Studio (see the module docstring)."""
    with zipfile.ZipFile(src) as z:
        order = [i.filename for i in z.infolist()]
        f = {n: z.read(n) for n in order}
    s = S.summarize(src)
    oid = {o['name']: k for k, o in s['objects'].items()}
    model = f['3D/3dmodel.model'].decode()
    ms = f['Metadata/model_settings.config'].decode()
    settings = f['Metadata/project_settings.config'].decode()
    ids = [int(i) for n in order if n.endswith('.model') for i in re.findall(r'<object id="(\d+)"', f[n].decode())]
    ident = max(int(i) for i in re.findall(r'key="identify_id" value="(\d+)"', ms))

    def obj_block(text, o):
        return re.search(r'  <object id="%s">.*?</object>\n' % o, text, re.S).group(0)

    # A global setting.
    assert '"wall_loops": "2"' in settings
    settings = settings.replace('"wall_loops": "2"', '"wall_loops": "3"', 1)

    # alpha: infill on the object, and a modifier inside it.
    a = oid['alpha']
    block = obj_block(ms, a)
    new = block.replace('<metadata key="extruder" value="1"/>\n', '<metadata key="extruder" value="1"/>\n    <metadata key="sparse_infill_density" value="40%"/>\n', 1)
    comp = re.search(r'<object id="%s"[^>]*>\s*<components>\s*(<component [^>]*/>)' % a, model).group(1)
    path = re.search(r'p:path="([^"]+)"', comp).group(1).lstrip('/')
    mid = max(ids) + 1
    ids.append(mid)
    f[path] = f[path].decode().replace('  </object>\n </resources>', '  </object>\n  <object id="%d" p:UUID="%s" type="other">\n   %s\n  </object>\n </resources>'
                                       % (mid, uuid.uuid4(), mesh_xml(box(10, 10, 10, -5, -5, -5))), 1).encode()
    assert 'type="other"' in f[path].decode()
    mcomp = '<component p:path="/%s" objectid="%d" p:UUID="%s" transform="1 0 0 0 1 0 0 0 1 %g %g %g"/>' % ((path, mid, uuid.uuid4()) + MOD_AT)
    model = model.replace(comp, comp + '\n    ' + mcomp, 1)
    new = new.replace('    </part>\n', '    </part>\n    <part id="%d" subtype="modifier_part">\n      <metadata key="name" value="infill box"/>\n'
                      '      <metadata key="matrix" value="1 0 0 %g 0 1 0 %g 0 0 1 %g 0 0 0 1"/>\n      <metadata key="sparse_infill_density" value="100%%"/>\n'
                      '      <mesh_stat face_count="12" edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n    </part>\n'
                      % ((mid,) + MOD_AT), 1)
    ms = ms.replace(block, new, 1)

    # beta: turned 90 degrees about its centre and moved, filament 2, its plate renamed.
    b = oid['beta']
    item = s['objects'][b]['items'][0]
    c = item['world']['centre']
    r = [0, 1, 0, -1, 0, 0, 0, 0, 1]  # x' = -y, y' = x
    turn = r + [c[0] - (c[0] * r[0] + c[1] * r[3]) + 20, c[1] - (c[0] * r[1] + c[1] * r[4]) + 10, 0]
    model = set_item(model, b, S.compose(item['transform'], turn))
    block = obj_block(ms, b)
    ms = ms.replace(block, block.replace('<metadata key="extruder" value="1"/>', '<metadata key="extruder" value="2"/>', 1), 1)
    ms = ms.replace('<metadata key="plater_name" value="beta"/>', '<metadata key="plater_name" value="beta tuned"/>', 1)

    # gamma: a second copy, its plate locked.
    g = oid['gamma']
    wid = max(ids) + 1
    ids.append(wid)
    gcomp = re.search(r'<object id="%s"[^>]*>\s*<components>\s*(<component [^>]*/>)' % g, model).group(1)
    copy_comp = re.sub(r'p:UUID="[^"]*"', 'p:UUID="%s"' % uuid.uuid4(), gcomp)
    model = model.replace(' </resources>', '  <object id="%d" p:UUID="%s" type="model">\n   <components>\n    %s\n   </components>\n  </object>\n </resources>'
                          % (wid, uuid.uuid4(), copy_comp), 1)
    gm = list(s['objects'][g]['items'][0]['transform'])
    gm[9] += COPY_DX
    model = model.replace(' </build>', '  <item objectid="%d" p:UUID="%s" transform="%s" printable="1"/>\n </build>' % (wid, uuid.uuid4(), fmt(gm)), 1)
    block = obj_block(ms, g)
    ms = ms.replace(block, block + block.replace('<object id="%s">' % g, '<object id="%d">' % wid, 1), 1)
    gplate = re.search(r'  <plate>(?:(?!</plate>).)*?<metadata key="object_id" value="%s"/>.*?</plate>\n' % g, ms, re.S).group(0)
    ident += 11
    locked = gplate.replace('<metadata key="locked" value="false"/>', '<metadata key="locked" value="true"/>', 1)
    locked = locked.replace('  </plate>\n', '    <model_instance>\n      <metadata key="object_id" value="%d"/>\n      <metadata key="instance_id" value="0"/>\n'
                            '      <metadata key="identify_id" value="%d"/>\n    </model_instance>\n  </plate>\n' % (wid, ident), 1)
    ms = ms.replace(gplate, locked, 1)

    # delta: renamed, moved onto plate 1, its own plate removed.
    d = oid['delta']
    block = obj_block(ms, d)
    ms = ms.replace(block, block.replace('value="delta"', 'value="delta renamed"').replace('<metadata key="name" value="delta.stl"/>', '<metadata key="name" value="delta renamed"/>'), 1)
    dplate = re.search(r'  <plate>(?:(?!</plate>).)*?<metadata key="object_id" value="%s"/>.*?</plate>\n' % d, ms, re.S).group(0)
    inst = re.search(r'    <model_instance>.*?</model_instance>\n', dplate, re.S).group(0)
    ms = ms.replace(dplate, '', 1)
    first = re.search(r'  <plate>.*?</plate>\n', ms, re.S).group(0)
    ms = ms.replace(first, first.replace('  </plate>\n', inst + '  </plate>\n', 1), 1)
    item = s['objects'][d]['items'][0]
    dm = list(item['transform'])
    dm[9] += DELTA_AT[0] - item['world']['centre'][0]
    dm[10] += DELTA_AT[1] - item['world']['centre'][1]
    model = set_item(model, d, dm)

    # Bambu Studio lists every object in cut_information.xml, numbered in order.
    cut = f['Metadata/cut_information.xml'].decode()
    n = len(re.findall(r'<object id=', cut)) + 1
    f['Metadata/cut_information.xml'] = cut.replace('</objects>', ' <object id="%d">\n  <cut_id id="0" check_sum="1" connectors_cnt="0"/>\n </object>\n</objects>' % n).encode()
    f['3D/3dmodel.model'] = model.encode()
    f['Metadata/model_settings.config'] = ms.encode()
    f['Metadata/project_settings.config'] = settings.encode()
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in order:
            z.writestr(n, f[n])
    return dst


# ---------- comparing a project before and after an update ----------

def close(a, b, tol=1e-6):
    """Two metadata values are the same: equal text, or the same numbers within tol."""
    if a == b:
        return True
    try:
        x, y = [float(v) for v in a.split()], [float(v) for v in b.split()]
    except (AttributeError, ValueError):
        return False
    return len(x) == len(y) and all(abs(p - q) <= tol for p, q in zip(x, y))


def dict_diff(a, b, skip=(), tol=1e-6):
    return ['%s: %s -> %s' % (k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if k not in skip and not close(a.get(k), b.get(k), tol)]


def turn_of(m):
    return [round(v, 6) + 0.0 for v in m[:9]]


def unchanged(old, new, oids):
    """What changed in these objects between two summaries: names, settings, parts, transforms, geometry."""
    out = []
    for oid in oids:
        a, b = old['objects'][oid], new['objects'].get(oid)
        if b is None:
            out.append('object %s is gone' % oid)
            continue
        n = a['name']
        out += ['%s: %s' % (n, x) for x in dict_diff(a['meta'], b['meta'])]
        if len(a['parts']) != len(b['parts']):
            out.append('%s: %d parts -> %d' % (n, len(a['parts']), len(b['parts'])))
        for pa, pb in zip(a['parts'], b['parts']):
            out += ['%s part %s: %s' % (n, pa['id'], x) for x in dict_diff(pa['meta'], pb['meta']) + dict_diff(pa['mesh_stat'] or {}, pb['mesh_stat'] or {})]
        for ca, cb in zip(a['components'], b['components']):
            if not close(' '.join(map(str, ca['transform'])), ' '.join(map(str, cb['transform'])), 1e-5):
                out.append('%s: component %s moved' % (n, ca['objectid']))
        if len(a['items']) != len(b['items']):
            out.append('%s: %d copies -> %d' % (n, len(a['items']), len(b['items'])))
        for ia, ib in zip(a['items'], b['items']):
            if not close(' '.join(map(str, ia['transform'])), ' '.join(map(str, ib['transform'])), 1e-5):
                out.append('%s: item moved %s -> %s' % (n, ia['transform'], ib['transform']))
            for k in ('size', 'centre'):
                if any(abs(x - y) > 1e-4 for x, y in zip(ia['world'][k], ib['world'][k])):
                    out.append('%s: world %s %s -> %s' % (n, k, ia['world'][k], ib['world'][k]))
    return out


def plates_same(old, new, n=None):
    """The first n plates (all by default) keep their names, locks and objects."""
    pa = [(p['name'], p['locked'], p['instances']) for p in old['plates']]
    pb = [(p['name'], p['locked'], p['instances']) for p in new['plates']][:len(pa) if n is None else n]
    return [] if pa == pb else ['plates %s -> %s' % (pa, pb)]


def spot(item):
    """Where a copy sits: the middle of its outline in x and y, and its lowest point."""
    w = item['world']
    return [w['centre'][0], w['centre'][1], w['lowest']]


class U(Case):

    @classmethod
    def setUpClass(cls):
        busy = bambu_running()
        if busy:
            raise unittest.SkipTest('Bambu Studio is running (%s), and update_3mf.py refuses then' % busy[0][:80])
        d = workdir('u-base')
        base = os.path.join(d, 'base.3mf')
        r = build(base, stl_files(d))
        if r.returncode != 0:
            raise RuntimeError('base build failed: ' + r.stderr[-800:])
        cls.tuned = tune(base, os.path.join(d, 'tuned.3mf'))
        cls.old = S.summarize(cls.tuned)
        cls.oid = {}
        for k, o in cls.old['objects'].items():
            cls.oid.setdefault(o['name'], []).append(k)
        cls.tuned_slices = None
        if slice_supported():
            ok, msg, _ = slice_project(cls.tuned, os.path.join(d, 'slice-tuned'))
            cls.tuned_slices = (ok, msg)
        wait_quiet()

    def run_update(self, name, stls, src=None, extra=()):
        """Copy the tuned project into run/NAME/ and update it. Returns (path, result)."""
        d = os.path.join(RUN, name)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name + '.3mf')
        shutil.copyfile(src or self.tuned, p)
        self.assertEqual(bambu_running(), [], 'a Bambu Studio process is still running')
        r = update(p, stls, extra)
        with open(os.path.join(d, 'update.log'), 'w') as f:
            f.write('$ update_3mf.py %s %s\n%s%s' % (p, ' '.join(list(stls) + list(extra)), r.stdout, r.stderr))
        return p, r

    def others(self, new, *changed):
        """Every object but the changed ones is the same as in the tuned project."""
        keep = [k for k in self.old['objects'] if self.old['objects'][k]['name'] not in changed]
        return unchanged(self.old, new, keep)

    def changed_ok(self, new, name, size):
        """The changed object keeps its settings, turn and spot, and has the new size."""
        out = []
        for k in self.oid[name]:
            a, b = self.old['objects'][k], new['objects'][k]
            out += ['%s: %s' % (name, x) for x in dict_diff(a['meta'], b['meta'], skip=('face_count',))]
            # The main part gets a new mesh, so its matrix, offset and face count change; the rest stays.
            moved = ('matrix', 'source_offset_x', 'source_offset_y', 'source_offset_z')
            for pa, pb in zip(a['parts'], b['parts']):
                main = pa['subtype'] == 'normal_part'
                out += ['%s part %s: %s' % (name, pa['meta'].get('name'), x) for x in dict_diff(pa['meta'], pb['meta'], skip=moved if main else ())]
                if not main:
                    out += ['%s part %s: %s' % (name, pa['meta'].get('name'), x) for x in dict_diff(pa['mesh_stat'] or {}, pb['mesh_stat'] or {})]
            for ia, ib in zip(a['items'], b['items']):
                if turn_of(ia['transform']) != turn_of(ib['transform']):
                    out.append('%s: turned %s -> %s' % (name, ia['transform'][:9], ib['transform'][:9]))
                if any(abs(x - y) > 1e-3 for x, y in zip(spot(ia), spot(ib))):
                    out.append('%s: moved from %s to %s' % (name, spot(ia), spot(ib)))
                if any(abs(x - y) > 1e-3 for x, y in zip(ib['world']['size'], size)):
                    out.append('%s: size %s, expected %s' % (name, ib['world']['size'], size))
        return out

    def assertSlicesNote(self, path, name):
        if self.tuned_slices and not self.tuned_slices[0]:
            self.fail('the tuned project itself does not slice, so this slice says nothing: %s' % self.tuned_slices[1])
        return self.assertSlices(path, name)

    # ---------- the scenarios ----------

    def test_U1_one_stl_changes(self):
        d = workdir('u1')
        p, r = self.run_update('u1', stl_files(d, {'alpha': box(30, 20, 20)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = S.summarize(p)
        problems = self.others(new, 'alpha') + self.changed_ok(new, 'alpha', [30, 20, 20]) + plates_same(self.old, new)
        if new['settings_sha1'] != self.old['settings_sha1']:
            problems.append('global settings changed')
        if sorted(new['files']) != sorted(self.old['files']):
            problems.append('files in the zip changed')
        self.assertEqual(problems, [])
        self.note('alpha 20 -> 30 mm: only its mesh changed; settings, modifier, copies, plates, names and filaments the same')

    def test_U2_keeps_its_spot(self):
        d = workdir('u2')
        p, r = self.run_update('u2', stl_files(d, {'beta': l_long(50)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = S.summarize(p)
        # beta is turned 90 degrees, so its 50 mm length runs along y.
        self.assertEqual(self.others(new, 'beta') + self.changed_ok(new, 'beta', [30, 50, 25]), [])
        self.note('beta (turned and moved) 40 -> 50 mm: same middle and bottom, same turn')

    def test_U3_two_copies(self):
        d = workdir('u3')
        p, r = self.run_update('u3', stl_files(d, {'gamma': box(15, 15, 20)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = S.summarize(p)
        self.assertEqual(len(self.oid['gamma']), 2)
        self.assertEqual(self.others(new, 'gamma') + self.changed_ok(new, 'gamma', [15, 15, 20]), [])
        g1, g2 = [new['objects'][k]['items'][0]['world']['centre'] for k in self.oid['gamma']]
        self.assertAlmostEqual(g2[0] - g1[0], COPY_DX, places=3)
        self.note('gamma 10 -> 20 mm tall: both copies changed, still %d mm apart' % COPY_DX)

    def test_U4_too_big_for_plate(self):
        lines = []
        # a) longer than the bed
        d = workdir('u4a')
        p, r = self.run_update('u4a', stl_files(d, {'beta': l_long(300)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        warn = [l for l in r.stdout.splitlines() if 'WARNING' in l and 'beta' in l]
        self.assertTrue(warn, 'no warning for a 300 mm beta:\n' + r.stdout)
        new = S.summarize(p)
        self.assertEqual(self.others(new, 'beta') + self.changed_ok(new, 'beta', [30, 300, 25]), [])
        lines.append('300 mm beta: "%s"' % warn[0].strip())
        # b) smaller than the bed, but it now crosses its plate's edge
        d = workdir('u4b')
        p, r = self.run_update('u4b', stl_files(d, {'delta': delta_wide(200)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = S.summarize(p)
        self.assertEqual(self.others(new, 'delta renamed') + self.changed_ok(new, 'delta renamed', [200, 30, 20]), [])
        warn = [l for l in r.stdout.splitlines() if 'WARNING' in l and 'delta' in l]
        self.assertTrue(warn, 'no warning for delta, now 200 mm wide and over plate 1\'s edge (x %.0f to %.0f):\n%s'
                        % (DELTA_AT[0] - 100, DELTA_AT[0] + 100, r.stdout))
        lines.append('200 mm delta over the plate edge: "%s"' % warn[0].strip())
        self.note('; '.join(lines) + '; nothing moved')

    def test_U5_new_stl(self):
        lines = []
        # a) one new STL: a fourth plate, the grid stays 2 x 2
        d = workdir('u5a')
        p, r = self.run_update('u5a', stl_files(d, extra={'epsilon': box(25, 10, 5)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = S.summarize(p)
        self.assertEqual(self.others(new) + plates_same(self.old, new, len(self.old['plates'])), [])
        self.assertEqual([pl['name'] for pl in new['plates']], ['alpha', 'beta tuned', 'gamma', 'epsilon'])
        eps = [k for k, o in new['objects'].items() if o['name'] == 'epsilon']
        self.assertEqual(len(eps), 1)
        self.assertEqual(new['plates'][3]['instances'], [(eps[0], '0')])
        bw, bh = new['bed']
        ox, oy = S.plate_origin(3, 4, bw, bh)
        w = new['objects'][eps[0]]['items'][0]['world']
        self.assertAlmostEqual(w['centre'][0], ox + bw / 2, places=3)
        self.assertAlmostEqual(w['centre'][1], oy + bh / 2, places=3)
        self.assertAlmostEqual(w['lowest'], 0, places=3)
        lines.append('epsilon: plate 4, centred; ' + self.assertSlicesNote(p, 'u5a'))
        # b) two new STLs: five plates, so the grid gets a third column and plate 3 moves
        d = workdir('u5b')
        p, r = self.run_update('u5b', stl_files(d, extra={'epsilon': box(25, 10, 5), 'zeta': box(10, 10, 30)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = S.summarize(p)
        self.assertEqual([pl['name'] for pl in new['plates']], ['alpha', 'beta tuned', 'gamma', 'epsilon', 'zeta'])
        self.assertEqual(plates_same(self.old, new, len(self.old['plates'])), [])
        # Nothing moved on its plate: each part keeps its spot measured from its own plate's corner.
        moved = []
        nold, nnew = len(self.old['plates']), len(new['plates'])
        for k, pl in enumerate(self.old['plates']):
            o0, o1 = S.plate_origin(k, nold, bw, bh), S.plate_origin(k, nnew, bw, bh)
            for oid, _ in pl['instances']:
                for ia, ib in zip(self.old['objects'][oid]['items'], new['objects'][oid]['items']):
                    a = [ia['world']['centre'][0] - o0[0], ia['world']['centre'][1] - o0[1]]
                    b = [ib['world']['centre'][0] - o1[0], ib['world']['centre'][1] - o1[1]]
                    if any(abs(x - y) > 1e-3 for x, y in zip(a, b)):
                        moved.append('%s on plate %d: %s -> %s from the plate corner' % (self.old['objects'][oid]['name'], k + 1, a, b))
        self.assertEqual(moved, [], 'parts left their plates when the grid got a new column')
        lines.append('epsilon + zeta: 5 plates, 3 columns, every part still on its plate; ' + self.assertSlicesNote(p, 'u5b'))
        self.note('; '.join(lines))

    def test_U6_stl_gone(self):
        d = workdir('u6')
        p, r = self.run_update('u6', stl_files(d, {'alpha': box(30, 20, 20)}, leave_out=('beta',)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        said = [l for l in r.stdout.splitlines() if 'beta' in l]
        self.assertTrue(said, 'beta, with no STL, is not reported:\n' + r.stdout)
        new = S.summarize(p)
        self.assertEqual(unchanged(self.old, new, self.oid['beta']) + plates_same(self.old, new), [])
        self.note('beta left out: "%s"; its object and plate stay' % said[0].strip())

    def test_U7_nothing_changed(self):
        d = workdir('u7')
        p, r = self.run_update('u7', stl_files(d))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('nothing changed', r.stdout.lower(), 'the run does not say nothing changed:\n' + r.stdout)
        self.assertEqual(sha1(p), sha1(self.tuned), 'the file changed although no STL did')
        self.note('same four STLs: file byte for byte the same; it says "%s"'
                  % next(l for l in r.stdout.splitlines() if 'nothing changed' in l.lower()).strip())

    def test_U14_not_approved(self):
        d = workdir('u14')
        p = os.path.join(d, 'u14.3mf')
        shutil.copyfile(self.tuned, p)
        r = run([sys.executable, UPDATE, p] + stl_files(d))
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('--approved', r.stderr)
        self.assertEqual(sha1(p), sha1(self.tuned), 'the file changed without --approved')
        self.note('stops: ' + r.stderr.strip().splitlines()[-1])

    def test_U15_down(self):
        # a) a new part turned with --down; a part already there keeps its turn
        d = workdir('u15')
        stls = stl_files(d, extra={'epsilon': l_block()})
        p, r = self.run_update('u15', stls, extra=['--down', 'epsilon=+x', '--down', 'beta=-y'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('beta is already in the project', r.stdout)
        new = S.summarize(p)
        self.assertEqual(self.others(new) + plates_same(self.old, new, len(self.old['plates'])), [])
        eps = [o for o in new['objects'].values() if o['name'] == 'epsilon']
        self.assertEqual(len(eps), 1)
        self.assertAlmostEqual(eps[0]['items'][0]['world']['area_z0'], L_FACES['+x'], delta=0.5)
        # b) a name that matches no STL: refused, the parts listed, the file left as it was
        p, r = self.run_update('u15b', stls, extra=['--down', 'ghost=-y'])
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('Traceback', r.stderr)
        for n in NAMES + ['epsilon', 'ghost']:
            self.assertIn(n, r.stderr)
        self.assertEqual(sha1(p), sha1(self.tuned), 'the file changed after an unknown --down part')
        self.note('epsilon=+x: new part lies on +x (%.0f mm2), beta keeps its turn; ghost=-y stops: %s'
                  % (eps[0]['items'][0]['world']['area_z0'], r.stderr.strip().splitlines()[-1]))

    def test_U16_xml_signs_in_names(self):
        # a) new parts whose names hold & < > ": the project reads back with those names
        d = workdir('u16')
        odd = {'a&b': box(25, 10, 5), 'c<d"e>': box(10, 10, 30)}
        p, r = self.run_update('u16', stl_files(d, extra=odd))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = S.summarize(p)  # reads every XML file in the zip: a bad sign stops it
        self.assertEqual(plates_same(self.old, new, len(self.old['plates'])), [])  # parts moving with their plate: U5
        self.assertEqual([pl['name'] for pl in new['plates']][-2:], ['a&b', 'c<d"e>'])
        for n in odd:
            self.assertEqual(sum(1 for o in new['objects'].values() if o['name'] == n), 1, n)
        # b) a&b changes: it is found by its file name and updated, not added again
        d2 = workdir('u16b')
        p2, r = self.run_update('u16b', stl_files(d2, extra=dict(odd, **{'a&b': box(35, 10, 5)})), src=p)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        again = S.summarize(p2)
        ab = [o for o in again['objects'].values() if o['name'] == 'a&b']
        self.assertEqual(len(ab), 1, 'a&b added a second time')
        self.assertEqual(len(again['plates']), len(new['plates']))
        self.assertEqual([round(v, 3) for v in ab[0]['items'][0]['world']['size']], [35, 10, 5])
        self.note('a&b and c<d"e> added, the XML reads back with those names; a&b changed: updated in place, no new plate')

    def test_U17_same_name_two_folders(self):
        d = workdir('u17')
        stls = stl_files(d)
        a = write_stl(os.path.join(d, 'a', 'gamma.stl'), box(30, 15, 10))
        p, r = self.run_update('u17', [s for s in stls if not s.endswith('gamma.stl')] + [stls[NAMES.index('gamma')], a])
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('Traceback', r.stderr)
        self.assertIn('two STLs are both named gamma', r.stderr)
        self.assertEqual(sha1(p), sha1(self.tuned), 'the file changed after two STLs with one name')
        self.note('stl/gamma.stl and a/gamma.stl: stops, "%s"' % r.stderr.strip().splitlines()[-1])

    def test_U18_new_part_after_modifier_file(self):
        # A new part is built from the lowest-numbered object file. When that file also holds a
        # modifier mesh, the modifier must not be copied into the new part with its id (audit F31).
        d = workdir('u18')
        src = os.path.join(d, 'modifier-first.3mf')
        with zipfile.ZipFile(self.tuned) as z:
            entries = [(i, z.read(i)) for i in z.infolist()]
        holder = [i.filename for i, b in entries if i.filename.startswith('3D/Objects/') and b'type="other"' in b][0]
        first = '3D/Objects/object_1.model'
        swap = {first: holder, holder: first}
        a, b = os.path.basename(first).encode(), os.path.basename(holder).encode()
        with zipfile.ZipFile(src, 'w', zipfile.ZIP_DEFLATED) as z:
            for i, data in entries:
                data = data.replace(a, b'@@').replace(b, a).replace(b'@@', b)
                z.writestr(swap.get(i.filename, i.filename), data)
        p, r = self.run_update('u18', stl_files(d, extra={'epsilon': box(25, 10, 5)}), src=src)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ids, extra = [], []
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if n.endswith('.model'):
                    found = re.findall(r'<object id="(\d+)"', z.read(n).decode())
                    ids += found
                    if n.startswith('3D/Objects/') and n not in swap and n not in [i.filename for i, _ in entries] and len(found) != 1:
                        extra.append('%s holds %d objects' % (n, len(found)))
        self.assertEqual(sorted(i for i in set(ids) if ids.count(i) > 1), [], 'object ids used twice')
        self.assertEqual(extra, [], 'the new part carries a copy of the modifier')
        new = S.summarize(p)
        alpha = [o for o in new['objects'].values() if o['name'] == 'alpha'][0]
        self.assertEqual(sum(1 for x in alpha['parts'] if x['subtype'] == 'modifier_part'), 1, 'alpha lost its modifier')
        self.note('modifier in %s, the template file: epsilon added with one object, no id used twice, alpha keeps its modifier; %s'
                  % (os.path.basename(first), self.assertSlicesNote(p, 'u18')))

    def test_U8_renamed_part(self):
        d = workdir('u8')
        p, r = self.run_update('u8', stl_files(d, {'delta': delta_wide(55)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = S.summarize(p)
        self.assertEqual(self.others(new, 'delta renamed') + self.changed_ok(new, 'delta renamed', [55, 30, 20]), [])
        o = new['objects'][self.oid['delta renamed'][0]]
        self.assertEqual(o['name'], 'delta renamed')
        self.assertEqual(o['parts'][0]['meta']['name'], 'delta renamed')
        self.note('delta.stl updated "delta renamed" (matched by source_file); names kept')

    def test_U9_modifier_kept(self):
        d = workdir('u9')
        p, r = self.run_update('u9', stl_files(d, {'alpha': box(30, 20, 20)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.oid['alpha'][0]
        before, after = S.Project(self.tuned), S.Project(p)
        oa, ob = self.old['objects'][k], after.summary()['objects'][k]
        mods = [(pa, pb) for pa, pb in zip(oa['parts'], ob['parts']) if pa['subtype'] == 'modifier_part']
        self.assertEqual(len(mods), 1, 'the modifier part is gone')
        pa, pb = mods[0]
        self.assertEqual(dict_diff(pa['meta'], pb['meta']) + dict_diff(pa['mesh_stat'], pb['mesh_stat']), [])
        comp = {c['objectid']: c for c in oa['components']}[pa['id']]
        self.assertEqual(before.local_tris(comp['path'], pa['id']), after.local_tris(comp['path'], pa['id']), 'the modifier mesh changed')
        # It sits at the same place in the part: same offset from the main part's corner (alpha grew in +x only).
        ia, ib = before.items[[i['objectid'] for i in before.items].index(k)], after.items[[i['objectid'] for i in after.items].index(k)]
        off = []
        for proj, it in ((before, ia), (after, ib)):
            main = S.stats(proj.world_tris(it))['min']
            mod = S.stats(proj.world_tris(it, part=pa['id']))['min']
            off.append([mod[j] - main[j] for j in range(3)])
        self.assertTrue(all(abs(x - y) < 1e-3 for x, y in zip(*off)), 'the modifier moved in the part: %s -> %s' % tuple(off))
        # Bambu Studio counts only the model parts in the object's face_count (seen in a project with modifiers).
        normal = sum(int(x['mesh_stat']['face_count']) for x in ob['parts'] if x['subtype'] == 'normal_part')
        self.assertEqual(int(ob['meta']['face_count']), normal, 'object face_count counts the modifier too')
        self.note('alpha 20 -> 30 mm: modifier settings, mesh and place in the part kept (offset %s)' % [round(v, 3) for v in off[1]])

    def test_U10_backup(self):
        lines = []
        backups = os.path.join(RUN, 'u10', '.backups')
        d = workdir('u10')
        p, r = self.run_update('u10', stl_files(d, {'alpha': box(30, 20, 20)}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        mine = [os.path.join(backups, f) for f in os.listdir(backups) if f.startswith('u10-')]
        good = [b for b in mine if sha1(b) == sha1(self.tuned)]
        self.assertTrue(good, 'no backup equal to the original among %s' % mine)
        shutil.copyfile(good[0], p)
        self.assertEqual(sha1(p), sha1(self.tuned))
        lines.append('backup %s equals the original; put back, byte for byte the same' % os.path.basename(good[0]))
        # b) an older backup with the same name (two updates in one second) must not be overwritten.
        d = workdir('u10b')
        backups = os.path.join(RUN, 'u10b', '.backups')
        os.makedirs(backups, exist_ok=True)
        now = time.time()
        held = []
        for s in range(-1, 8):
            h = os.path.join(backups, 'u10b-%s.3mf' % time.strftime('%Y%m%d-%H%M%S', time.localtime(now + s)))
            with open(h, 'w') as f:
                f.write('an older backup')
            held.append(h)
        try:
            p, r = self.run_update('u10b', stl_files(d, {'alpha': box(30, 20, 20)}))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            lost = []
            for h in held:
                with open(h, 'rb') as f:
                    if f.read() != b'an older backup':
                        lost.append(os.path.basename(h))
            self.assertEqual(lost, [], 'an older backup was overwritten')
            mine = [os.path.join(backups, f) for f in os.listdir(backups) if f.startswith('u10b-')]
            self.assertTrue([b for b in mine if sha1(b) == sha1(self.tuned)], 'no backup equal to the original')
        finally:
            for h in held:
                if os.path.exists(h):
                    os.remove(h)
        lines.append('an older backup of the same name is kept')
        self.note('; '.join(lines))

    def test_U11_bambu_running(self):
        # The stand-in is /bin/sleep started under Bambu Studio's path, so its command line holds that
        # path. A copy of /bin/sleep at that path, as the plan says, is killed by macOS at start (exit 137).
        fake = os.path.join(TMP, 'BambuStudio.app', 'Contents', 'MacOS', 'BambuStudio')
        d = workdir('u11')
        stls = stl_files(d, {'alpha': box(30, 20, 20)})
        proc = subprocess.Popen([fake, '300'], executable='/bin/sleep')
        try:
            time.sleep(0.5)
            self.assertTrue(bambu_running(), 'the stand-in does not show as Bambu Studio')
            p = os.path.join(d, 'u11.3mf')
            shutil.copyfile(self.tuned, p)
            r = update(p, stls)
            with open(os.path.join(d, 'update.log'), 'w') as f:
                f.write(r.stdout + r.stderr)
        finally:
            proc.kill()
            proc.wait()
        self.assertNotEqual(r.returncode, 0, 'the update ran while Bambu Studio was running')
        self.assertIn('save and quit', r.stdout + r.stderr)
        self.assertEqual(sha1(p), sha1(self.tuned), 'the file changed')
        self.assertEqual(bambu_running(), [], 'the stand-in is still running')
        self.note('stand-in running: refused with "%s"; file untouched' % (r.stdout + r.stderr).strip().splitlines()[-1][:110])

    def test_U12_slices_and_twice(self):
        d = workdir('u12')
        stls = stl_files(d, {'alpha': box(30, 20, 20)})
        p, r = self.run_update('u12', stls)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        first = sha1(p)
        r2 = update(p, stls)
        with open(os.path.join(d, 'update2.log'), 'w') as f:
            f.write(r2.stdout + r2.stderr)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(sha1(p), first, 'the update of the update changed the file')
        sliced = self.assertSlicesNote(p, 'u12')
        self.note('U1 run twice: second run changed nothing; %s; the tuned project %s'
                  % (sliced, 'slices' if self.tuned_slices and self.tuned_slices[0] else 'slice: %s' % (self.tuned_slices,)))

    def test_U13_spacing_by_object(self):
        # The template prints by object, so parts on one plate need extruder_clearance_max_radius
        # (68 mm) between them. alpha grows from its middle towards delta, which sits on plate 1 too.
        a = self.old['objects'][self.oid['alpha'][0]]['items'][0]['world']['centre']
        dl = self.old['objects'][self.oid['delta renamed'][0]]['items'][0]['world']['centre']

        def gap(w):  # alpha w x w, delta 30 x 30, both outlines
            return math.hypot(*(max(0, abs(dl[j] - a[j]) - w / 2 - 15) for j in range(2)))

        # The same project with plate 1 set to print by layer in Bambu Studio: its own order wins.
        d = workdir('u13c')
        by_layer = os.path.join(d, 'plate1-by-layer.3mf')
        with zipfile.ZipFile(self.tuned) as z:
            order = [i.filename for i in z.infolist()]
            f = {n: z.read(n) for n in order}
        ms = f['Metadata/model_settings.config'].decode()
        line = '    <metadata key="plater_id" value="1"/>\n'
        self.assertIn(line, ms)
        f['Metadata/model_settings.config'] = ms.replace(line, line + '    <metadata key="print_sequence" value="by layer"/>\n', 1).encode()
        with zipfile.ZipFile(by_layer, 'w', zipfile.ZIP_DEFLATED) as z:
            for n in order:
                z.writestr(n, f[n])

        lines = []
        for name, w, src, want in (('u13a', 70, None, True), ('u13b', 40, None, False), ('u13c', 70, by_layer, False)):
            p, r = self.run_update(name, stl_files(workdir(name) if src is None else d, {'alpha': box(w, w, 20)}), src)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            warn = [l.strip() for l in r.stdout.splitlines() if 'WARNING' in l and 'apart' in l]
            self.assertEqual(bool(warn), want, '%s: alpha %d mm, %.0f mm from delta, %s:\n%s'
                             % (name, w, gap(w), 'plate 1 by layer' if src else 'by object', r.stdout))
            if want:
                self.assertTrue('alpha' in warn[0] and 'delta renamed' in warn[0] and 'plate 1' in warn[0], warn[0])
            lines.append('alpha %d mm (%.0f mm from delta)%s: %s' % (w, gap(w), ', plate 1 by layer' if src else '',
                                                                    '"%s"' % warn[0] if warn else 'no warning'))
        self.note('; '.join(lines))


def wait_quiet(seconds=30):
    """Wait until no Bambu Studio process is left from a build or slice."""
    end = time.time() + seconds
    while bambu_running() and time.time() < end:
        time.sleep(1)


if __name__ == '__main__':
    unittest.main()
