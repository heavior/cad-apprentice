"""Group B of 3dprinting/3mf-test-scenarios.md: build_3mf.py builds a project from STLs.

Run: TMPDIR=3dprinting/tests/run/tmp/ python3 -m unittest test_build_3mf   (from this folder)
or all groups through run_tests.py.
"""
import json, os, re, shutil, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa
import summary as S

AXIS = {'x': 0, 'y': 1, 'z': 2}


def face_area(tris, face):
    """Area of the STL's triangles lying on the named outer face (-z = the bottom as drawn)."""
    k = AXIS[face[1]]
    pts = [p for t in tris for p in t]
    v = min(p[k] for p in pts) if face[0] == '-' else max(p[k] for p in pts)
    return sum(S.tri_area(*t) for t in tris if all(abs(p[k] - v) < 1e-4 for p in t))


def zip_problems(path):
    """§ 2 check 7: the zip reads, and every file its content types and _rels name is in it."""
    z = zipfile.ZipFile(path)
    bad = z.testzip()
    if bad:
        return ['bad CRC in %s' % bad]
    names = set(z.namelist())
    out = []
    ct = ET.fromstring(z.read('[Content_Types].xml'))
    for el in ct:
        if el.tag.endswith('Override') and el.get('PartName', '').lstrip('/') not in names:
            out.append('content types name a missing %s' % el.get('PartName'))
    for n in names:
        if n.endswith('.rels'):
            for el in ET.fromstring(z.read(n)):
                t = el.get('Target', '')
                if t.startswith('/'):
                    t = t[1:]
                else:  # relative to the folder that holds _rels
                    t = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(n)), t))
                if t not in names:
                    out.append('%s names a missing %s' % (n, el.get('Target')))
    return out


def check_build(case, out, stls, down=None, ref=TEMPLATE_3MF, stdout='', do_slice=True, name='out'):
    """Every check of § 2 (9, the project files, runs once around the whole night). Returns notes."""
    down = down or {}
    case.assertTrue(os.path.exists(out), 'no output file %s' % out)
    case.assertEqual(zip_problems(out), [])  # 7
    p = S.Project(out)
    s = p.summary()
    bw, bh = s['bed']
    ref_settings = zipfile.ZipFile(ref).read('Metadata/project_settings.config')
    case.assertEqual(p.raw['Metadata/project_settings.config'], ref_settings, 'settings not copied byte for byte')  # 4
    parts = [os.path.splitext(os.path.basename(x))[0] for x in stls]
    case.assertEqual([pl['name'] for pl in s['plates']], parts, 'plates not one per part, in order')  # 1
    case.assertEqual([pl['id'] for pl in s['plates']], list(range(1, len(parts) + 1)))
    n = len(parts)
    big = []
    for k, (pl, part, stl) in enumerate(zip(s['plates'], parts, stls)):
        case.assertEqual(len(pl['instances']), 1, 'plate %d holds %d objects' % (k + 1, len(pl['instances'])))
        oid = pl['instances'][0][0]
        o = s['objects'][oid]
        case.assertEqual(o['name'], part)  # 6
        case.assertNotIn('.stl', o['name'])
        case.assertEqual(o['extruder'], '1')  # 5
        for prt in o['parts']:
            case.assertEqual(prt['meta'].get('extruder', '1'), '1')
        case.assertEqual(len(o['items']), 1)
        w = o['items'][0]['world']
        # 3: the mesh kept, turned if --down was given
        tris = S.read_stl(stl)
        st = S.stats(tris)
        face = down.get(part, '-z')
        k_up = AXIS[face[1]]
        exp_plane = sorted(st['size'][j] for j in range(3) if j != k_up)
        case.assertAlmostEqual(w['size'][2], st['size'][k_up], delta=0.01, msg='%s height' % part)
        for a, b in zip(sorted(w['size'][:2]), exp_plane):
            case.assertAlmostEqual(a, b, delta=0.01, msg='%s footprint %s vs %s' % (part, w['size'][:2], exp_plane))
        case.assertAlmostEqual(w['volume'], st['volume'], delta=abs(st['volume']) * 0.001, msg='%s volume' % part)
        fa = face_area(tris, face)
        case.assertAlmostEqual(w['area_low'], fa, delta=max(0.01, fa * 0.001), msg='%s: face %s is not the one down' % (part, face))
        # 2: centred on its own plate, on the plate, inside the bed or warned
        ox, oy = S.plate_origin(k, n, bw, bh)
        case.assertAlmostEqual(w['centre'][0], ox + bw / 2, delta=0.01, msg='%s x centre' % part)
        case.assertAlmostEqual(w['centre'][1], oy + bh / 2, delta=0.01, msg='%s y centre' % part)
        case.assertAlmostEqual(w['lowest'], 0, delta=0.01, msg='%s lowest point' % part)
        if w['size'][0] > bw or w['size'][1] > bh:
            big.append(part)
            case.assertIn('WARNING: %s' % part, stdout)
        else:
            case.assertGreaterEqual(w['min'][0], ox - 0.01)
            case.assertGreaterEqual(w['min'][1], oy - 0.01)
            case.assertLessEqual(w['max'][0], ox + bw + 0.01)
            case.assertLessEqual(w['max'][1], oy + bh + 0.01)
    notes = ['%d plates, checks 1-7 pass' % n]
    if do_slice and not big:
        notes.append(case.assertSlices(out, name))  # 8
    elif big:
        notes.append('not sliced: %s bigger than the bed' % ', '.join(big))
    return notes


def stl_set(folder, shapes, ascii_names=()):
    """Write {name: triangles} as STLs into folder; returns the paths in order."""
    return [write_stl(os.path.join(folder, n + '.stl'), t, ascii=n in ascii_names) for n, t in shapes]


FAKE_MARK = '''#!/bin/sh
touch "%s"
exec "%s" "$@"
'''

# Bambu Studio's command line, then every component of the export turned 90 degrees about z with
# its mesh turned back, so where each part sits doesn't change, only how the transform says it.
FAKE_TURN = r'''#!/usr/bin/env python3
import re, subprocess, sys, zipfile
REAL = %r
p = subprocess.run([REAL] + sys.argv[1:])
if p.returncode:
    sys.exit(p.returncode)
out = sys.argv[sys.argv.index('--export-3mf') + 1]
z = zipfile.ZipFile(out)
order = [i.filename for i in z.infolist()]
files = {n: z.read(n) for n in order}
z.close()
R = [0, 1, 0, -1, 0, 0, 0, 0, 1]      # x -> -y... rows of a point-times-matrix turn
RI = [0, -1, 0, 1, 0, 0, 0, 0, 1]     # the turn back
def mul(a, b):
    lin = [sum(a[3 * r + j] * b[3 * j + c] for j in range(3)) for r in range(3) for c in range(3)]
    t = [a[9 + 0] * b[c] + a[9 + 1] * b[3 + c] + a[9 + 2] * b[6 + c] + b[9 + c] for c in range(3)] if len(a) > 9 else [b[9 + c] for c in range(3)]
    return lin + t
model = files['3D/3dmodel.model'].decode()
turned = []
def comp(m):
    tag = m.group(0)
    t = list(map(float, re.search(r'transform="([^"]+)"', tag).group(1).split()))
    new = mul(R + [0, 0, 0], t)
    turned.append((re.search(r'p:path="([^"]+)"', tag).group(1).lstrip('/'), re.search(r'objectid="(\d+)"', tag).group(1)))
    return re.sub(r'transform="[^"]+"', 'transform="%%s"' %% ' '.join(repr(v) for v in new), tag)
model = re.sub(r'<component [^>]*/>', comp, model)
files['3D/3dmodel.model'] = model.encode()
for path, oid in turned:
    text = files[path].decode()
    def obj(m):
        def v(mm):
            x, y, zz = float(mm.group(1)), float(mm.group(2)), float(mm.group(3))
            q = (x * RI[0] + y * RI[3] + zz * RI[6], x * RI[1] + y * RI[4] + zz * RI[7], x * RI[2] + y * RI[5] + zz * RI[8])
            return '<vertex x="%%r" y="%%r" z="%%r"/>' %% q
        return re.sub(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"/>', v, m.group(0))
    text = re.sub(r'<object id="%%s"[^>]*>.*?</object>' %% oid, obj, text, count=1, flags=re.S)
    files[path] = text.encode()
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for n in order:
        z.writestr(n, files[n])
'''


def build_with(bambu, out, stls, down=None, settings_from=None, tmp=None, raw_down=()):
    """build_3mf.py with its BAMBU pointed at another program, in its own TMPDIR."""
    args = [out, '--approved', 'test run'] + list(stls)
    for part, face in (down or {}).items():
        args += ['--down', '%s=%s' % (part, face)]
    for d in raw_down:
        args += ['--down', d]
    if settings_from:
        args += ['--settings-from', settings_from]
    code = 'import sys; sys.path.insert(0, %r); import build_3mf; build_3mf.BAMBU = %r; sys.argv = %r; build_3mf.main()' % (
        PRINT, bambu, ['build_3mf.py'] + args)
    e = env()
    if tmp:
        e['TMPDIR'] = tmp + '/'
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=e, timeout=600, cwd=RUN)


def marker_bambu(folder):
    """A Bambu Studio stand-in that leaves a file behind when it runs, then runs the real one."""
    mark = os.path.join(folder, 'bambu-ran')
    fake = os.path.join(folder, 'bambu-mark.sh')
    with open(fake, 'w') as f:
        f.write(FAKE_MARK % (mark, BAMBU))
    os.chmod(fake, 0o755)
    return fake, mark


def leftovers(tmp):
    """Folders left in a test's TMPDIR, except Bambu Studio's own."""
    return sorted(n for n in os.listdir(tmp) if n != 'bamboo_model')


class B(Case):

    # ---------- the gaps, first (plan § 4 step 2) ----------

    def gap_setup(self, name):
        d = workdir(name)
        tmp = os.path.join(d, 'tmp')
        os.makedirs(tmp)
        fake, mark = marker_bambu(d)
        return d, tmp, fake, mark

    def assertCleanError(self, r, out, tmp, mark=None, words=()):
        msg = (r.stdout + r.stderr).strip()
        self.assertNotEqual(r.returncode, 0, 'no error: ' + msg)
        self.assertNotIn('Traceback', r.stderr, 'a Python traceback, not a clear error: ' + r.stderr[-600:])
        for w in words:
            self.assertIn(w, msg)
        self.assertFalse(os.path.exists(out), 'an output file was written')
        self.assertEqual(leftovers(tmp), [], 'temp folder left behind')
        if mark:
            self.assertFalse(os.path.exists(mark), 'Bambu Studio ran before the error')
        return msg.splitlines()[-1]

    def test_B21_not_approved(self):
        d, tmp, fake, mark = self.gap_setup('b21')
        stls = stl_set(d, [('cube', box(20, 20, 20))])
        out = os.path.join(d, 'out.3mf')
        for extra in ([], ['--approved', ' ']):
            with self.subTest(approved=extra):
                code = 'import sys; sys.path.insert(0, %r); import build_3mf; build_3mf.BAMBU = %r; sys.argv = %r; build_3mf.main()' % (
                    PRINT, fake, ['build_3mf.py', out] + stls + extra)
                e = env()
                e['TMPDIR'] = tmp + '/'
                r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=e, timeout=600, cwd=RUN)
                last = self.assertCleanError(r, out, tmp, mark, words=['--approved'])
        self.note('error: ' + last)

    def test_B13_down_missing_part(self):
        d, tmp, fake, mark = self.gap_setup('b13')
        stls = stl_set(d, [('cube', box(20, 20, 20))])
        out = os.path.join(d, 'out.3mf')
        r = build_with(fake, out, stls, down={'ghost': '-y'}, tmp=tmp)
        last = self.assertCleanError(r, out, tmp, mark, words=['ghost'])
        self.note('error: ' + last)

    def test_B14_down_bad_face(self):
        d, tmp, fake, mark = self.gap_setup('b14')
        stls = stl_set(d, [('cube', box(20, 20, 20))])
        out = os.path.join(d, 'out.3mf')
        lines = []
        for raw in ('cube=-q', 'cube'):
            with self.subTest(down=raw):
                r = build_with(fake, out, stls, raw_down=[raw], tmp=tmp)
                lines.append(self.assertCleanError(r, out, tmp, mark, words=FACES))
        self.note('errors: ' + ' / '.join(lines))

    def test_B15_same_name_two_folders(self):
        d, tmp, fake, mark = self.gap_setup('b15')
        a = write_stl(os.path.join(d, 'a', 'part.stl'), box(20, 20, 20))
        b = write_stl(os.path.join(d, 'b', 'part.stl'), box(30, 10, 5))
        out = os.path.join(d, 'out.3mf')
        r = build_with(fake, out, [a, b], tmp=tmp)
        last = self.assertCleanError(r, out, tmp, mark, words=['part.stl'])
        self.note('error: ' + last)

    def test_B16_bambu_fails(self):
        d, tmp, fake, mark = self.gap_setup('b16')
        empty = os.path.join(d, 'empty.stl')
        open(empty, 'w').close()
        out = os.path.join(d, 'out.3mf')
        r = build_with(BAMBU, out, [empty], tmp=tmp)
        # Bambu Studio's own words for it, seen on 2.07: "Loading of a model file failed."
        self.assertCleanError(r, out, tmp, words=['Loading of a model file failed'])
        # An open mesh: Bambu Studio loads it, so it must build or fail cleanly.
        opened = write_stl(os.path.join(d, 'open.stl'), open_cube())
        out2 = os.path.join(d, 'open.3mf')
        r2 = build_with(BAMBU, out2, [opened], tmp=tmp)
        self.assertNotIn('Traceback', r2.stderr)
        self.assertEqual(leftovers(tmp), [])
        self.note('empty STL: Bambu\'s lines in the error, temp folder gone; open mesh: %s' % (
            'builds' if r2.returncode == 0 else 'clean error'))

    def test_B17_component_turn(self):
        d = workdir('b17')
        stls = stl_set(d, [('lblock', l_block()), ('bar', box(120, 20, 10)), ('cube', box(20, 20, 20))])
        # Does Bambu Studio's own --arrange 1 turn anything? Look at a plain export with a long bar.
        raw = os.path.join(d, 'raw.3mf')
        bar = write_stl(os.path.join(d, 'longbar.stl'), box(240, 8, 8))
        P = '/Applications/BambuStudio.app/Contents/Resources/profiles/BBL'
        p = subprocess.run([BAMBU, '--load-settings', P + '/machine/Bambu Lab X1 Carbon 0.4 nozzle.json;' + P + '/process/0.20mm Standard @BBL X1C.json',
                        '--load-filaments', P + '/filament/Bambu PLA Matte @BBL X1C.json', '--load-filament-ids', '1,1,1,1',
                        '--arrange', '1', '--export-3mf', raw] + stls + [bar], capture_output=True, text=True, env=env(), cwd=d, timeout=600)
        self.assertTrue(os.path.exists(raw), 'plain export failed: ' + (p.stdout + p.stderr)[-600:])
        pr = S.Project(raw)
        comp_turns = sum(1 for cs in pr.wrappers.values() for c in cs if [round(v, 6) for v in c['transform'][:9]] != [1, 0, 0, 0, 1, 0, 0, 0, 1])
        item_turns = sum(1 for i in pr.items if [round(v, 6) for v in i['transform'][:9]] != [1, 0, 0, 0, 1, 0, 0, 0, 1])
        # The stand-in turns every component; the build must come out the same as a plain one.
        fake = os.path.join(d, 'bambu-turn.py')
        with open(fake, 'w') as f:
            f.write(FAKE_TURN % BAMBU)
        os.chmod(fake, 0o755)
        out = os.path.join(d, 'turned.3mf')
        r = build_with(fake, out, stls, down={'lblock': '-y'})
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertNotEqual([c['transform'][:9] for c in S.Project(out).wrappers[list(S.Project(out).wrappers)[0]]][0][:2], [1, 0], 'stand-in did not turn')
        notes = check_build(self, out, stls, down={'lblock': '-y'}, stdout=r.stdout, name='turned')
        self.note('plain export: %d component turns, %d item turns (build_3mf replaces the item transform); with turned components: %s'
                  % (comp_turns, item_turns, '; '.join(notes)))

    def test_B18_filament_per_part(self):
        self.skipTest('skipped: the --filament option is not built (plan § 5)')

    def test_B19_reference_without_settings(self):
        d, tmp, fake, mark = self.gap_setup('b19')
        stls = stl_set(d, [('cube', box(20, 20, 20))])
        plain = os.path.join(d, 'plain.3mf')
        with zipfile.ZipFile(plain, 'w') as z:
            z.writestr('3D/3dmodel.model', '<model/>')
        notzip = os.path.join(d, 'notzip.3mf')
        with open(notzip, 'w') as f:
            f.write('not a zip')
        lines = []
        for ref in (plain, notzip, os.path.join(d, 'missing.3mf')):
            with self.subTest(ref=os.path.basename(ref)):
                out = os.path.join(d, 'out.3mf')
                r = build_with(fake, out, stls, settings_from=ref, tmp=tmp)
                lines.append(self.assertCleanError(r, out, tmp, mark, words=[os.path.basename(ref)]))
        self.note('errors: ' + ' / '.join(lines))

    # ---------- the rest of B ----------

    def test_B1_one_stl(self):
        d = workdir('b1')
        stls = stl_set(d, [('cube', box(20, 20, 20))])
        out = os.path.join(d, 'b1.3mf')
        r = build(out, stls)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        notes = check_build(self, out, stls, stdout=r.stdout, name='b1')
        # The checks must catch a broken file too: the part moved 5 mm, then the settings changed.
        for what, fname, change in (('moved', '3D/3dmodel.model', lambda t: re.sub(r'(<item [^>]*transform="(?:\S+ ){9})(\S+)', lambda m: m.group(1) + str(float(m.group(2)) + 5), t)),
                                    ('settings', 'Metadata/project_settings.config', lambda t: t.replace('"wall_loops": "2"', '"wall_loops": "3"'))):
            bad = os.path.join(d, 'b1-%s.3mf' % what)
            with zipfile.ZipFile(out) as zi, zipfile.ZipFile(bad, 'w') as zo:
                for i in zi.infolist():
                    data = zi.read(i.filename)
                    zo.writestr(i, change(data.decode()).encode() if i.filename == fname else data)
            self.assertNotEqual(sha1(bad), sha1(out))
            with self.assertRaises(AssertionError, msg='checks missed a %s part' % what):
                check_build(self, bad, stls, stdout=r.stdout, do_slice=False)
        self.note('; '.join(notes) + '; a part moved 5 mm and a changed setting are both caught')

    def test_B2_six_stls(self):
        d = workdir('b2')
        stls = stl_set(d, [('p%d' % i, box(10 + 5 * i, 20, 5 + i)) for i in range(1, 7)])
        out = os.path.join(d, 'b2.3mf')
        r = build(out, stls)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        notes = check_build(self, out, stls, stdout=r.stdout, name='b2')
        s = S.summarize(out)
        xs = sorted({round(o['items'][0]['world']['centre'][0], 1) for o in s['objects'].values()})
        ys = sorted({round(o['items'][0]['world']['centre'][1], 1) for o in s['objects'].values()})
        self.assertEqual(len(xs), 3, 'not 3 columns: %s' % xs)
        self.assertEqual(len(ys), 2, 'not 2 rows: %s' % ys)
        self.note('rows of 3 at x %s, y %s; %s' % (xs, ys, '; '.join(notes)))

    def test_B3_grid_sizes(self):
        done, sliced = [], []
        for n in (1, 2, 3, 4, 5, 7, 9, 10):
            with self.subTest(n=n):
                d = workdir('b3/n%d' % n)
                stls = stl_set(d, [('c%02d' % i, box(10 + i, 10 + 2 * i, 5)) for i in range(n)])
                out = os.path.join(d, 'b3-%d.3mf' % n)
                r = build(out, stls)
                self.assertEqual(r.returncode, 0, r.stderr[-800:])
                notes = check_build(self, out, stls, stdout=r.stdout, name='n%d' % n)
                s = S.summarize(out)
                cols = len({round(o['items'][0]['world']['centre'][0], 1) for o in s['objects'].values()})
                self.assertEqual(cols, math.ceil(math.sqrt(n) - 1e-9))
                done.append('%d:%d' % (n, cols))
                sliced.append(notes[-1].startswith('slices'))
        self.note('n:columns %s, %s' % (' '.join(done), 'all sliced' if sliced and all(sliced) else
                                        '%d of %d sliced' % (sum(sliced), len(sliced))))

    def test_B4_each_face_down(self):
        got = []
        for face in FACES:
            with self.subTest(face=face):
                d = workdir('b4/%s' % face.replace('-', 'm').replace('+', 'p'))
                stls = stl_set(d, [('lblock', l_block())])
                out = os.path.join(d, 'b4.3mf')
                r = build(out, stls, down={'lblock': face})
                self.assertEqual(r.returncode, 0, r.stderr[-800:])
                check_build(self, out, stls, down={'lblock': face}, stdout=r.stdout, name='b4')
                w = list(S.summarize(out)['objects'].values())[0]['items'][0]['world']
                self.assertAlmostEqual(w['area_z0'], L_FACES[face], delta=0.5)
                self.assertAlmostEqual(w['volume'], L_VOLUME, delta=L_VOLUME * 0.001)
                got.append('%s %.0f' % (face, w['area_z0']))
        self.note('area on the plate: ' + ', '.join(got))

    def test_B5_down_one_of_several(self):
        d = workdir('b5')
        stls = stl_set(d, [('la', l_block()), ('lb', l_block()), ('lc', l_block())])
        out = os.path.join(d, 'b5.3mf')
        r = build(out, stls, down={'lb': '+x'})
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        notes = check_build(self, out, stls, down={'lb': '+x'}, stdout=r.stdout, name='b5')
        s = S.summarize(out)
        area = {o['name']: round(o['items'][0]['world']['area_z0']) for o in s['objects'].values()}
        self.assertEqual(area, {'la': 1200, 'lb': 300, 'lc': 1200})
        self.note('area down %s; %s' % (area, '; '.join(notes)))

    def test_B6_bigger_than_bed(self):
        d = workdir('b6')
        stls = stl_set(d, [('cube', box(20, 20, 20)), ('longbar', long_bar())])
        out = os.path.join(d, 'b6.3mf')
        r = build(out, stls)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        warn = [l for l in r.stdout.splitlines() if l.startswith('WARNING')]
        self.assertEqual(len(warn), 1, r.stdout)
        self.assertIn('longbar', warn[0])
        self.assertIn('300', warn[0])
        self.assertIn('256', warn[0])
        check_build(self, out, stls, stdout=r.stdout, name='b6')
        self.note('warning: ' + warn[0])

    def test_B7_output_exists(self):
        d = workdir('b7')
        stls = stl_set(d, [('cube', box(20, 20, 20))])
        out = os.path.join(d, 'tuned.3mf')
        shutil.copy(TEMPLATE_3MF, out)
        before = sha1(out)
        r = build(out, stls)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('exists', r.stderr)
        self.assertEqual(sha1(out), before)
        self.note('stops: ' + r.stderr.strip().splitlines()[-1])

    def test_B8_hole_and_overhang(self):
        d = workdir('b8')
        stls = stl_set(d, [('holed', holed_overhang())])
        out = os.path.join(d, 'b8.3mf')
        r = build(out, stls)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        notes = check_build(self, out, stls, stdout=r.stdout, name='b8')
        p = S.Project(out)
        world = p.world_tris(p.items[0])
        src = S.read_stl(stls[0])
        self.assertEqual(len(world), len(src), 'faces lost or merged')
        self.assertTrue(S.same_shape(world, src), 'mesh changed')
        self.note('%d triangles kept, same shape; %s' % (len(src), '; '.join(notes)))

    def test_B9_binary_and_ascii(self):
        d = workdir('b9')
        stls = stl_set(d, [('bin_cube', box(20, 20, 20)), ('ascii_lblock', l_block())], ascii_names=('ascii_lblock',))
        self.assertTrue(open(stls[1], 'rb').read(5) == b'solid')
        out = os.path.join(d, 'b9.3mf')
        r = build(out, stls)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.note('; '.join(check_build(self, out, stls, stdout=r.stdout, name='b9')))

    def test_B10_spaces_and_letters(self):
        d = workdir('b10')
        folder = os.path.join(d, 'папка с пробелами', 'Модель é')
        stls = stl_set(folder, [('куб тест', box(20, 20, 20)), ('part two', l_block())])
        out = os.path.join(d, 'выход проект.3mf')
        r = build(out, stls)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.note('; '.join(check_build(self, out, stls, stdout=r.stdout, name='b10')))

    def test_B11_other_reference(self):
        notes = []
        with self.subTest(ref='own'):
            if not OTHER_REF or not os.path.exists(OTHER_REF):
                notes.append('B11_REF_3MF not set or missing: skipped')
            else:
                d = workdir('b11/own')
                ref = os.path.join(d, 'own-copy.3mf')
                shutil.copy(OTHER_REF, ref)
                stls = stl_set(d, [('cube', box(20, 20, 20)), ('lblock', l_block())])
                out = os.path.join(d, 'b11.3mf')
                r = build(out, stls, settings_from=ref)
                self.assertEqual(r.returncode, 0, r.stderr[-800:])
                n = check_build(self, out, stls, ref=ref, stdout=r.stdout, name='b11')
                bed = S.summarize(out)['bed']
                notes.append('%s (bed %gx%g): %s' % (os.path.basename(OTHER_REF), bed[0], bed[1], '; '.join(n)))
        with self.subTest(ref='180 bed'):
            # A reference with a smaller bed, made from the template: only printable_area changes.
            d = workdir('b11/bed180')
            ref = os.path.join(d, 'bed180.3mf')
            with zipfile.ZipFile(TEMPLATE_3MF) as zi, zipfile.ZipFile(ref, 'w', zipfile.ZIP_DEFLATED) as zo:
                for i in zi.infolist():
                    data = zi.read(i.filename)
                    if i.filename == 'Metadata/project_settings.config':
                        js = json.loads(data)
                        js['printable_area'] = ['0x0', '180x0', '180x180', '0x180']
                        data = json.dumps(js, indent=4).encode()
                    zo.writestr(i, data)
            stls = stl_set(d, [('c%d' % i, box(20 + 10 * i, 20, 10)) for i in range(4)])
            out = os.path.join(d, 'b11b.3mf')
            r = build(out, stls, settings_from=ref)
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            n = check_build(self, out, stls, ref=ref, stdout=r.stdout, name='b11b')
            self.assertEqual(S.summarize(out)['bed'], [180, 180])
            notes.append('180 mm bed: plates laid out on 180 x 1.2; %s' % '; '.join(n))
        self.note(' | '.join(notes))

    def test_B12_twice_same(self):
        d = workdir('b12')
        stls = stl_set(d, [('cube', box(20, 20, 20)), ('lblock', l_block()), ('holed', holed_overhang())])
        outs = []
        for k in (1, 2):
            out = os.path.join(d, 'b12-%d.3mf' % k)
            r = build(out, stls, down={'lblock': '+y'})
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            outs.append(out)
        a, b = S.summarize(outs[0]), S.summarize(outs[1])
        # The plan asks for the same plates, transforms and meshes. The order of files inside the
        # zip is not one of them: Bambu Studio writes the mesh files in a different order each run.
        order_same = a['files'] == b['files']
        for s in (a, b):
            s.pop('path')
            s['files'] = sorted(s['files'])
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        pa, pb = S.Project(outs[0]), S.Project(outs[1])
        meshes = [n for n in pa.names if n.startswith('3D/Objects/')]
        same = [n for n in meshes if pa.raw[n] == pb.raw[n]]
        self.assertEqual(same, meshes, 'mesh files differ')
        diff = sorted(n for n in pa.names if pa.raw[n] != pb.raw.get(n))
        self.note('same plates, transforms and meshes; files that differ in bytes: %s; zip file order %s'
                  % (', '.join(diff) or 'none', 'the same' if order_same else 'differs (Bambu Studio writes mesh files in any order)'))

    def test_B20_plate_pictures(self):
        d = workdir('b20')
        stls = stl_set(d, [('a', box(20, 20, 20)), ('b', box(30, 20, 10)), ('c', box(10, 10, 30))])
        out = os.path.join(d, 'b20.3mf')
        r = build(out, stls)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        s = S.summarize(out)
        keys = ('thumbnail_file', 'thumbnail_no_light_file', 'top_file', 'pick_file')
        self.assertTrue(all(k in s['plates'][0]['meta'] for k in keys))
        for k in keys:
            self.assertIn(s['plates'][0]['meta'][k], s['files'])
        for pl in s['plates'][1:]:
            self.assertFalse(any(k in pl['meta'] for k in keys))
        notes = check_build(self, out, stls, stdout=r.stdout, name='b20')
        self.note('pictures on plate 1 only; ' + '; '.join(notes))

    def test_B22_xml_signs_in_names(self):
        d = workdir('b22')
        stls = stl_set(d, [('a&b', box(20, 20, 20)), ('c<d"e>', l_block())])
        out = os.path.join(d, 'b22.3mf')
        r = build(out, stls)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        s = S.summarize(out)  # reads every XML file in the zip: a bad sign stops it
        self.assertEqual([pl['name'] for pl in s['plates']], ['a&b', 'c<d"e>'])
        notes = check_build(self, out, stls, stdout=r.stdout, name='b22')
        self.note('parts a&b and c<d"e>: the XML reads back, plates named after them; ' + '; '.join(notes))

    def test_B23_written_whole(self):
        d = workdir('b23')
        stls = stl_set(d, [('a', box(20, 20, 20))])
        out = os.path.join(d, 'b23.3mf')
        r = build(out, stls)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        left = [n for n in os.listdir(d) if n.endswith('.tmp')]
        self.assertEqual(left, [], 'temp files left behind')
        self.assertIsNone(zipfile.ZipFile(out).testzip())
        self.note('written to a temp file and linked in; no .tmp left, the zip reads')


if __name__ == '__main__':
    unittest.main()
