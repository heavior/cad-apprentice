"""Shared parts of the 3MF tests: paths, test STLs, running the scripts and Bambu Studio's slicer.

Plan: 3dprinting/3mf-test-scenarios.md. Everything is written under run/ (git-ignored), and the
scripts run with TMPDIR set to run/tmp/.
"""
import hashlib, json, math, os, shutil, struct, subprocess, sys, unittest, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.abspath(os.path.join(HERE, '..', '..'))
PRINT = os.path.join(KIT, '3dprinting')
# The repo the kit sits in: every .3mf under its projects/ is checked before and after the tests.
ROOT = os.path.abspath(os.path.join(KIT, '..', '..', '..'))
BUILD = os.path.join(PRINT, 'build_3mf.py')
UPDATE = os.path.join(PRINT, 'update_3mf.py')
TEMPLATE = os.path.join(PRINT, 'template.3mf')
BAMBU = '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'
RUN = os.path.join(HERE, 'run')
TMP = os.path.join(RUN, 'tmp')
RESULTS = os.path.join(RUN, 'results')
# B11's own .3mf with other printer settings, if you have one. Unset: that part of B11 is skipped.
OTHER_REF = os.environ.get('B11_REF_3MF', '')
FACES = ['-z', '+z', '-x', '+x', '-y', '+y']

for d in (RUN, TMP, RESULTS):
    os.makedirs(d, exist_ok=True)

# One-line notes per test, written into the results by run_tests.py.
NOTES = {}


def note(test, text):
    NOTES[test.id().split('.')[-1]] = text


def env():
    e = dict(os.environ)
    e['TMPDIR'] = TMP + '/'
    return e


def workdir(name):
    """A fresh folder under run/ for one test."""
    d = os.path.join(RUN, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    return d


def sha1(path):
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def project_3mfs():
    """sha1 of every .3mf under projects/ (read only), but not the tests' own run/ folder."""
    out = {}
    for base, dirs, files in os.walk(os.path.join(ROOT, 'projects')):
        if os.path.abspath(base) == RUN:
            dirs[:] = []
            continue
        for f in files:
            if f.lower().endswith('.3mf'):
                p = os.path.join(base, f)
                out[os.path.relpath(p, ROOT)] = sha1(p)
    return out


# ---------- test STLs ----------

def normal(t):
    """Unit normal of a triangle. Real normals matter: Bambu Studio reads a binary STL as ASCII
    when the 128 bytes after the header hold no byte above 127, which zero normals and small round
    coordinates (an L-block of 0, 10 and 15 mm) can cause."""
    a, b, c = t
    u = [b[k] - a[k] for k in range(3)]
    v = [c[k] - a[k] for k in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    l = math.sqrt(sum(x * x for x in n)) or 1
    return tuple(x / l for x in n)


def write_stl(path, tris, ascii=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if ascii:
        with open(path, 'w') as f:
            f.write('solid test\n')
            for t in tris:
                f.write(' facet normal %.6f %.6f %.6f\n  outer loop\n' % normal(t))
                for p in t:
                    f.write('   vertex %.6f %.6f %.6f\n' % p)
                f.write('  endloop\n endfacet\n')
            f.write('endsolid test\n')
    else:
        with open(path, 'wb') as f:
            f.write(b'test stl'.ljust(80, b' ') + struct.pack('<I', len(tris)))
            for t in tris:
                f.write(struct.pack('<3f', *normal(t)) + struct.pack('<9f', *[c for p in t for c in p]) + b'\0\0')
    return path


def grid_solid(xs, ys, zs, filled):
    """A closed mesh from a grid of cells: filled(i, j, k) says which cells are solid. Faces between
    a solid and an empty cell become two triangles each, facing out."""
    nx, ny, nz = len(xs) - 1, len(ys) - 1, len(zs) - 1

    def full(i, j, k):
        return 0 <= i < nx and 0 <= j < ny and 0 <= k < nz and filled(i, j, k)
    tris = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                if not full(i, j, k):
                    continue
                x0, x1, y0, y1, z0, z1 = xs[i], xs[i + 1], ys[j], ys[j + 1], zs[k], zs[k + 1]
                quads = []
                if not full(i - 1, j, k): quads.append([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)])
                if not full(i + 1, j, k): quads.append([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)])
                if not full(i, j - 1, k): quads.append([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)])
                if not full(i, j + 1, k): quads.append([(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)])
                if not full(i, j, k - 1): quads.append([(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)])
                if not full(i, j, k + 1): quads.append([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])
                for a, b, c, d in quads:
                    tris += [(a, b, c), (a, c, d)]
    return tris


def box(sx, sy, sz, x0=0, y0=0, z0=0):
    return grid_solid([x0, x0 + sx], [y0, y0 + sy], [z0, z0 + sz], lambda i, j, k: True)


def l_block():
    """A 40 x 30 x 10 slab with a 15 x 10 x 15 block on one corner. Every outer face has its own
    area, so the face at z = 0 tells which one is down: -z 1200, +z 150, -x 450, +x 300, -y 625, +y 400."""
    return grid_solid([0, 15, 40], [0, 10, 30], [0, 10, 25], lambda i, j, k: k == 0 or (i == 0 and j == 0))


L_FACES = {'-z': 1200, '+z': 150, '-x': 450, '+x': 300, '-y': 625, '+y': 400}
L_VOLUME = 40 * 30 * 10 + 15 * 10 * 15


def long_bar():
    """300 x 12 x 10 mm: longer than the 256 mm bed."""
    return box(300, 12, 10)


def holed_overhang():
    """A 30 x 30 x 20 block with a 10 x 10 hole through it and an arm sticking out at the top."""
    xs, ys, zs = [0, 10, 20, 30, 45], [0, 10, 20, 30], [0, 15, 20]
    return grid_solid(xs, ys, zs, lambda i, j, k: (i < 3 and not (i == 1 and j == 1)) or (i == 3 and k == 1 and j == 1))


def open_cube():
    """A 20 mm cube with its top missing: an open mesh."""
    return [t for t in box(20, 20, 20) if not all(abs(p[2] - 20) < 1e-9 for p in t)]


def mesh_volume(tris):
    from summary import tri_volume
    return sum(tri_volume(*t) for t in tris)


# ---------- running things ----------

def run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, env=env(), timeout=timeout, cwd=RUN)


def build(out, stls, down=None, settings_from=None, extra=()):
    cmd = [sys.executable, BUILD, out, '--approved', 'test run'] + list(stls)
    for part, face in (down or {}).items():
        cmd += ['--down', '%s=%s' % (part, face)]
    if settings_from:
        cmd += ['--settings-from', settings_from]
    return run(cmd + list(extra))


def update(project, stls, extra=()):
    return run([sys.executable, UPDATE, project, '--approved', 'test run'] + list(stls) + list(extra))


def bambu_running():
    """Lines of any process whose command line holds Bambu Studio's binary."""
    ps = subprocess.run(['ps', '-axwwo', 'pid=,command='], capture_output=True, text=True).stdout
    return [l.strip() for l in ps.splitlines() if 'BambuStudio.app/Contents/MacOS/BambuStudio' in l]


SLICE_SUPPORTED = None


def slice_supported():
    """Bambu Studio's command line lists --slice and slices a plain cube project (checked once)."""
    global SLICE_SUPPORTED
    if SLICE_SUPPORTED is None:
        helped = subprocess.run([BAMBU, '--help'], capture_output=True, text=True, env=env(), timeout=120, cwd=RUN)
        SLICE_SUPPORTED = '--slice' in helped.stdout + helped.stderr
    return SLICE_SUPPORTED


def slice_project(path, outdir):
    """Slice every plate. Returns (ok, message, result.json data)."""
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
    os.makedirs(outdir)
    p = subprocess.run([BAMBU, '--slice', '0', '--outputdir', outdir, os.path.abspath(path)],
                       capture_output=True, text=True, env=env(), timeout=1800, cwd=outdir)
    with open(os.path.join(outdir, 'bambu.log'), 'w') as f:
        f.write(p.stdout + p.stderr)
    res = os.path.join(outdir, 'result.json')
    data = {}
    if os.path.exists(res):
        with open(res) as f:
            data = json.load(f)
    warnings = [pl.get('warning_message') for pl in data.get('sliced_plates', []) if pl.get('warning_message')]
    ok = p.returncode == 0 and data.get('return_code') == 0 and not warnings
    msg = 'exit %d, %s%s' % (p.returncode, data.get('error_string', 'no result.json'), (' warnings: ' + ' | '.join(warnings)) if warnings else '')
    return ok, msg, data


class Case(unittest.TestCase):
    maxDiff = None

    def note(self, text):
        note(self, text)

    def skip_part(self, why):
        """A check of this test that couldn't run: the test is reported as a skip, not a pass."""
        self.skipped_parts = getattr(self, 'skipped_parts', []) + [why]

    def assertSlices(self, path, name):
        """§ 2 check 8: every plate slices with no error or warning."""
        if not slice_supported():
            self.skip_part('slicing %s: --slice not in this Bambu Studio' % name)
            return 'slice skipped: --slice not in this Bambu Studio'
        ok, msg, data = slice_project(path, os.path.join(os.path.dirname(path), 'slice-' + name))
        self.assertTrue(ok, 'slicing %s failed: %s' % (path, msg))
        gcode = [f for f in os.listdir(os.path.join(os.path.dirname(path), 'slice-' + name)) if f.endswith('.gcode')]
        return 'slices (%d plates)' % len(gcode)
