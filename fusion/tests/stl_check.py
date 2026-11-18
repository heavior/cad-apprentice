# Checks exported STL files without Fusion (spec N8): every edge is shared by exactly two triangles,
# going opposite ways (watertight, faces turned the same way), the mesh is one piece, and its size.
# Plain Python, no numpy. Usage: python3 stl_check.py <file.stl> [...]; prints one JSON line per file.
import json, struct, sys


def read(path):
    data = open(path, 'rb').read()
    if len(data) >= 84:
        n = struct.unpack('<I', data[80:84])[0]
        if len(data) == 84 + 50 * n:
            tris = []
            for i in range(n):
                v = struct.unpack('<9f', data[84 + 50 * i + 12:84 + 50 * i + 48])
                tris.append((v[0:3], v[3:6], v[6:9]))
            return tris
    # ASCII
    tris, cur = [], []
    for line in data.decode('ascii', 'replace').splitlines():
        w = line.split()
        if w and w[0] == 'vertex':
            cur.append(tuple(float(x) for x in w[1:4]))
            if len(cur) == 3:
                tris.append(tuple(cur))
                cur = []
    return tris


def check(path, digits=5):
    tris = read(path)
    ids, pts = {}, []
    def vid(p):
        k = tuple(round(c, digits) for c in p)
        if k not in ids:
            ids[k] = len(pts)
            pts.append(k)
        return ids[k]
    faces = []
    degenerate = 0
    for t in tris:
        f = tuple(vid(p) for p in t)
        if len(set(f)) < 3:
            degenerate += 1
            continue
        faces.append(f)
    edges = {}
    for f in faces:
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            edges[(a, b)] = edges.get((a, b), 0) + 1
    open_edges = flipped = 0
    for (a, b), n in edges.items():
        back = edges.get((b, a), 0)
        if n > 1:
            flipped += 1  # the same edge twice the same way: a face turned over, or more than 2 faces
        if back == 0:
            open_edges += 1
    # Pieces: triangles joined by shared vertices.
    parent = list(range(len(pts)))
    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for f in faces:
        for v in f[1:]:
            ra, rb = root(f[0]), root(v)
            if ra != rb:
                parent[ra] = rb
    pieces = len(set(root(v) for f in faces for v in f))
    lo = [min(p[i] for p in pts) for i in range(3)] if pts else None
    hi = [max(p[i] for p in pts) for i in range(3)] if pts else None
    return {'file': path, 'triangles': len(tris), 'degenerate': degenerate, 'open_edges': open_edges, 'same_way_edges': flipped,
            'pieces': pieces, 'min': lo, 'max': hi, 'size': [round(b - a, 4) for a, b in zip(lo, hi)] if pts else None,
            'ok': open_edges == 0 and flipped == 0 and pieces == 1}


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(json.dumps(check(p)))
