"""Turn a Bambu Studio .3mf into a plain summary, for the 3MF tests (3dprinting/3mf-test-scenarios.md § 1).

Reads the zip the way Bambu Studio writes it, with its own XML parser, so it doesn't share the
scripts' regexes. What it gives:
- plates: number, name, locked, and which objects are on each
- objects: name, filament, every setting, parts (with subtype and settings), components and copies
- each object's mesh after its transforms: size, centre, volume, lowest point, and the area of
  triangles lying on z = 0
- the global settings file and the bed size

Usage: python3 summary.py FILE.3mf   (prints the summary as JSON)
"""
import hashlib, json, math, re, sys, zipfile
import xml.etree.ElementTree as ET

CORE = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
PROD = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
GAP = 1.2  # plates sit one bed plus a fifth apart (Bambu Studio's layout)


def numbers(s):
    return [float(v) for v in s.split()] if s else list(IDENTITY)


def apply(m, p):
    """A point times a 3MF transform (12 numbers, rows of a 4x3 matrix)."""
    return tuple(p[0] * m[k] + p[1] * m[3 + k] + p[2] * m[6 + k] + m[9 + k] for k in range(3))


def compose(inner, outer):
    """The transform that applies inner first, then outer."""
    lin = [sum(inner[3 * r + j] * outer[3 * j + c] for j in range(3)) for r in range(3) for c in range(3)]
    t = apply(outer, inner[9:12])
    return lin + list(t)


def tri_area(a, b, c):
    u = [b[k] - a[k] for k in range(3)]
    v = [c[k] - a[k] for k in range(3)]
    x = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return math.sqrt(sum(w * w for w in x)) / 2


def tri_volume(a, b, c):
    return (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6


def stats(tris, eps=1e-4):
    """Size, centre, volume, lowest point and the area lying on z = 0 of a list of triangles."""
    if not tris:
        return {'triangles': 0}
    pts = [p for t in tris for p in t]
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    return {
        'triangles': len(tris),
        'min': lo, 'max': hi,
        'size': [hi[k] - lo[k] for k in range(3)],
        'centre': [(hi[k] + lo[k]) / 2 for k in range(3)],
        'volume': sum(tri_volume(*t) for t in tris),
        'lowest': lo[2],
        'area_z0': sum(tri_area(*t) for t in tris if all(abs(p[2]) < eps for p in t)),
        # the same at the lowest point, for parts that sit a hair off z = 0
        'area_low': sum(tri_area(*t) for t in tris if all(abs(p[2] - lo[2]) < 1e-3 for p in t)),
    }


def shape_key(tris, digits=3):
    """The triangles moved so their outline is centred on 0, each started at its smallest corner
    (winding kept), rounded and sorted: equal keys mean the same mesh, wherever it sits."""
    pts = [p for t in tris for p in t]
    if not pts:
        return []
    c = [(min(p[k] for p in pts) + max(p[k] for p in pts)) / 2 for k in range(3)]
    out = []
    for t in tris:
        t = [tuple(round(p[k] - c[k], digits) + 0.0 for k in range(3)) for p in t]
        i = t.index(min(t))
        out.append(tuple(t[i:] + t[:i]))
    return sorted(out)


def same_shape(a, b, tol=2e-3):
    ka, kb = shape_key(a), shape_key(b)
    if len(ka) != len(kb):
        return False
    return all(abs(x - y) <= tol for ta, tb in zip(ka, kb) for pa, pb in zip(ta, tb) for x, y in zip(pa, pb))


def read_stl(path):
    """Triangles of a binary or ASCII STL."""
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) >= 84:
        n = int.from_bytes(data[80:84], 'little')
        if len(data) == 84 + 50 * n:
            import struct
            return [tuple(tuple(v[3 * j:3 * j + 3]) for j in range(3)) for v in
                    (struct.unpack_from('<9f', data, 84 + 50 * i + 12) for i in range(n))]
    v = [tuple(map(float, m)) for m in re.findall(rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)', data)]
    return [tuple(v[i:i + 3]) for i in range(0, len(v), 3)]


def bed_size(settings_text):
    area = json.loads(settings_text)['printable_area']
    xs, ys = zip(*(map(float, p.split('x')) for p in area))
    return max(xs), max(ys)


def plate_origin(k, n_plates, bw, bh):
    """Lower-left corner of plate k (0-based) when there are n_plates: rows of ceil(sqrt(n))."""
    cols = math.ceil(math.sqrt(n_plates) - 1e-9)
    return (k % cols) * bw * GAP, -(k // cols) * bh * GAP


def meta(el):
    out = {}
    for m in el.findall('metadata'):
        if m.get('key') is not None:
            out[m.get('key')] = m.get('value')
        else:
            out.update({k: v for k, v in m.attrib.items()})
    return out


class Project:
    def __init__(self, path):
        self.path = path
        z = zipfile.ZipFile(path)
        self.names = z.namelist()
        self.raw = {n: z.read(n) for n in self.names}
        self.model = ET.fromstring(self.raw['3D/3dmodel.model'])
        self.settings_text = self.raw.get('Metadata/project_settings.config', b'').decode()
        self.ms = ET.fromstring(self.raw['Metadata/model_settings.config']) if 'Metadata/model_settings.config' in self.raw else None
        self._meshes = {}
        # wrapper objects: id -> components
        self.wrappers = {}
        for o in self.model.iter(CORE + 'object'):
            comps = o.find(CORE + 'components')
            if comps is not None:
                self.wrappers[o.get('id')] = [{
                    'objectid': c.get('objectid'),
                    'path': (c.get(PROD + 'path') or '/3D/3dmodel.model').lstrip('/'),
                    'transform': numbers(c.get('transform')),
                } for c in comps.findall(CORE + 'component')]
        self.items = [{'objectid': i.get('objectid'), 'transform': numbers(i.get('transform')), 'printable': i.get('printable')}
                      for i in self.model.iter(CORE + 'item')]

    def mesh(self, path, oid):
        """(type, vertices, triangles) of mesh object oid in the file path."""
        key = (path, oid)
        if key not in self._meshes:
            root = ET.fromstring(self.raw[path])
            for o in root.iter(CORE + 'object'):
                m = o.find(CORE + 'mesh')
                if m is None:
                    continue
                verts = [(float(v.get('x')), float(v.get('y')), float(v.get('z'))) for v in m.iter(CORE + 'vertex')]
                tris = [(int(t.get('v1')), int(t.get('v2')), int(t.get('v3'))) for t in m.iter(CORE + 'triangle')]
                self._meshes[(path, o.get('id'))] = (o.get('type'), verts, tris)
        return self._meshes[key]

    def subtypes(self, oid):
        """part id -> subtype, from model_settings."""
        out = {}
        if self.ms is not None:
            for o in self.ms.findall('object'):
                if o.get('id') == oid:
                    out.update({p.get('id'): p.get('subtype') for p in o.findall('part')})
        return out

    def world_tris(self, item, model_parts_only=True, part=None):
        """Triangles of one build item after component and item transforms."""
        sub = self.subtypes(item['objectid'])
        out = []
        for c in self.wrappers.get(item['objectid'], []):
            if part is not None and c['objectid'] != part:
                continue
            typ, verts, tris = self.mesh(c['path'], c['objectid'])
            if model_parts_only and part is None and (typ == 'other' or sub.get(c['objectid'], 'normal_part') != 'normal_part'):
                continue
            m = compose(c['transform'], item['transform'])
            w = [apply(m, v) for v in verts]
            out += [(w[a], w[b], w[c2]) for a, b, c2 in tris]
        return out

    def local_tris(self, path, oid):
        typ, verts, tris = self.mesh(path, oid)
        return [(verts[a], verts[b], verts[c]) for a, b, c in tris]

    def summary(self):
        bw, bh = bed_size(self.settings_text) if self.settings_text else (None, None)
        objects = {}
        if self.ms is not None:
            for o in self.ms.findall('object'):
                oid = o.get('id')
                objects[oid] = {
                    'name': meta(o).get('name'),
                    'extruder': meta(o).get('extruder'),
                    'meta': meta(o),
                    'parts': [{'id': p.get('id'), 'subtype': p.get('subtype'), 'meta': meta(p),
                               'mesh_stat': (p.find('mesh_stat').attrib if p.find('mesh_stat') is not None else None)}
                              for p in o.findall('part')],
                    'components': self.wrappers.get(oid, []),
                    'items': [],
                }
        for i in self.items:
            o = objects.setdefault(i['objectid'], {'name': None, 'extruder': None, 'meta': {}, 'parts': [], 'components': self.wrappers.get(i['objectid'], []), 'items': []})
            o['items'].append({'transform': i['transform'], 'printable': i['printable'], 'world': stats(self.world_tris(i))})
        plates = []
        if self.ms is not None:
            for p in self.ms.findall('plate'):
                pm = meta(p)
                plates.append({
                    'id': int(pm.get('plater_id', 0)), 'name': pm.get('plater_name'), 'locked': pm.get('locked'),
                    'meta': pm,
                    'instances': [(meta(mi).get('object_id'), meta(mi).get('instance_id')) for mi in p.findall('model_instance')],
                })
        return {
            'path': self.path,
            'files': self.names,
            'bed': [bw, bh],
            'settings_sha1': hashlib.sha1(self.settings_text.encode()).hexdigest(),
            'plates': plates,
            'objects': objects,
        }


def summarize(path):
    return Project(path).summary()


def plate_of(summary):
    """object id -> plate index (0-based, in file order)."""
    out = {}
    for k, p in enumerate(summary['plates']):
        for oid, _ in p['instances']:
            out[oid] = k
    return out


if __name__ == '__main__':
    print(json.dumps(summarize(sys.argv[1]), indent=1, default=str))
