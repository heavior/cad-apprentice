"""Swap new STLs into a Bambu Studio .3mf and keep everything the person set up in it.

The person tunes the project in Bambu Studio: settings, orientation, copies, plates. So
a design round changes only the meshes. Each part whose source_file is the STL's name gets the new
mesh; transforms, settings, filaments and plates stay. See 3dprinting/rules.md.

Usage:
  python3 <kit>/3dprinting/update_3mf.py PROJECT.3mf --approved "<their words>" [--down PART=-y ...] a.stl b.stl ...

--approved "..."  the person's OK on the changed design, in their words, as in build_3mf.py. Required.

--down PART=FACE  for a new part only: the face that goes on the plate, as in build_3mf.py. A part
                  already in the project keeps the turn it was given. PART must be one of the STLs.

- A changed part keeps its spot: the middle of its outline stays put and its bottom stays on the plate.
- An STL that matches no part becomes a new object on a new plate, named after it, on filament 1.
- A part that now sticks out over its plate's edge, or is bigger than the bed, gets a warning.
- On a plate that prints by object (the template does, on purpose), parts closer
  than the print head's clearance (extruder_clearance_max_radius, 68 mm) get a warning. A plate's own
  print order, set in Bambu Studio, wins over the project's.
- When a new plate gives the plate grid a new column, every part moves with its plate.
- A part with no STL given is left alone and listed. So is an STL whose mesh hasn't changed.
- When no STL changed, the file is not written at all.
- Refuses while any Bambu Studio is running (it may have the file open), and backs the file up first.
- Refuses two STLs with the same file name: parts are matched by file name.
- Reads back every file it changed before saving, and refuses to save if one doesn't parse or the
  count of objects, parts, copies or plates isn't the one expected.
"""
import math, os, re, shutil, struct, subprocess, sys, time, uuid, zipfile
import xml.etree.ElementTree as ET

from build_3mf import DOWN, GAP, approved, bed_size, part_names, xml_attr, xml_text

IDENTITY = '1 0 0 0 1 0 0 0 1 0 0 0'


def attrs(tag):
    return dict(re.findall(r'([\w:]+)="([^"]*)"', tag))


def apply(m, p, move=True):
    """A point times a 3MF transform (12 numbers, rows of a 4x3 matrix)."""
    t = m[9:12] if move else (0, 0, 0)
    return tuple(p[0] * m[k] + p[1] * m[3 + k] + p[2] * m[6 + k] + t[k] for k in range(3))


def box(pts):
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    return lo, hi


def fmt(vals):
    return ' '.join('%.9g' % v for v in vals)


def read_stl(path):
    data = open(path, 'rb').read()
    n = struct.unpack_from('<I', data, 80)[0] if len(data) >= 84 else -1
    if len(data) == 84 + 50 * n:
        return [(t[0:3], t[3:6], t[6:9]) for t in (struct.unpack_from('<9f', data, 84 + 50 * i + 12) for i in range(n))]
    v = [tuple(map(float, m)) for m in re.findall(rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)', data)]
    return [tuple(v[i:i + 3]) for i in range(0, len(v), 3)]


def new_mesh(path):
    """The STL as a Bambu mesh: shared vertices, centred on its outline like Bambu Studio does."""
    idx, verts, faces = {}, [], []
    for t in read_stl(path):
        f = []
        for p in t:
            if p not in idx:
                idx[p] = len(verts)
                verts.append(p)
            f.append(idx[p])
        if len(set(f)) == 3:
            faces.append(f)
    lo, hi = box(verts)
    c = [(lo[k] + hi[k]) / 2 for k in range(3)]
    verts = [tuple(p[k] - c[k] for k in range(3)) for p in verts]
    xml = ('<mesh>\n    <vertices>\n' + ''.join('     <vertex x="%.9g" y="%.9g" z="%.9g"/>\n' % p for p in verts)
           + '    </vertices>\n    <triangles>\n' + ''.join('     <triangle v1="%d" v2="%d" v3="%d"/>\n' % tuple(f) for f in faces)
           + '    </triangles>\n   </mesh>')
    return xml, verts, c, len(faces)


def mesh_verts(text, mid):
    body = re.search(r'<object id="%s"[^>]*>\s*<mesh>(.*?)</mesh>' % mid, text, re.S).group(1)
    return [tuple(map(float, m)) for m in re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', body)]


def mesh_tris(body):
    """The triangles of a mesh's XML, each as three points."""
    v = [tuple(map(float, m)) for m in re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', body)]
    return [(v[int(a)], v[int(b)], v[int(c)]) for a, b, c in re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', body)]


def same_mesh(a, b, tol=1e-4):
    """Two lists of triangles are the same mesh, in any order, within tol mm. Bambu Studio keeps
    32-bit numbers, so a mesh read back from its file differs from the STL in the last digits."""
    if len(a) != len(b):
        return False

    def order(tris):
        out = []
        for t in tris:
            r = [tuple(round(x, 3) for x in p) for p in t]
            i = r.index(min(r))  # start at the smallest corner, keep the winding
            out.append((r[i:] + r[:i], tuple(t[i:]) + tuple(t[:i])))
        return [t for _, t in sorted(out)]
    return all(abs(x - y) <= tol for ta, tb in zip(order(a), order(b)) for pa, pb in zip(ta, tb) for x, y in zip(pa, pb))


def spacing_check(settings, blocks, plate_of, boxes, items, names, world, old_meshes):
    """Printing by object, the head prints one part to the top before the next, so parts on one plate
    need the head's clearance between them. The check uses outlines (boxes), which are never smaller
    than the part, so it may warn where Bambu Studio's own check would pass, but never misses one."""
    seq = re.search(r'"print_sequence":\s*"([^"]*)"', settings)
    seq = seq.group(1) if seq else 'by layer'  # Bambu Studio's default
    # A plate's own print order (set in Bambu Studio) wins over the project's: a plate can be
    # "by layer" in a "by object" project.
    by_object = set()
    for k, body in enumerate(blocks):
        own = re.search(r'key="print_sequence" value="([^"]*)"', body)
        if (own.group(1) if own else seq) == 'by object':
            by_object.add(k)
    if not by_object:
        return
    r = re.search(r'"extruder_clearance_max_radius":\s*"([^"]*)"', settings) or re.search(r'"extruder_clearance_radius":\s*"([^"]*)"', settings)
    if not r:
        print('WARNING: printing by object, but the project has no extruder clearance setting, so part spacing was not checked')
        return
    clear = float(r.group(1))
    seen, on_plate = {}, {}
    for _, a in items:
        oid = a['objectid']
        n = seen[oid] = seen.get(oid, -1) + 1
        k = plate_of.get((oid, n))
        if k not in by_object or oid not in names:
            continue
        if (oid, n) not in boxes:
            boxes[(oid, n)] = world(oid, list(map(float, a.get('transform', IDENTITY).split())), old_meshes(oid))
        on_plate.setdefault(k, []).append((oid, n))
    for k, copies in sorted(on_plate.items()):
        for i, c1 in enumerate(copies):
            for c2 in copies[i + 1:]:
                (l1, h1), (l2, h2) = boxes[c1], boxes[c2]
                gap = math.hypot(*(max(0, l2[j] - h1[j], l1[j] - h2[j]) for j in range(2)))
                if gap < clear:
                    print('WARNING: plate %d: %s and %s are %.0f mm apart; printing by object needs %.0f mm. '
                          'Move them apart in Bambu Studio' % (k + 1, names[c1[0]], names[c2[0]], gap, clear))


def local(el):
    return el.tag.rsplit('}', 1)[-1]


def counts(model, ms):
    """How many objects, parts, copies (build items) and plates the project holds, read as XML."""
    m, c = ET.fromstring(model.encode()), ET.fromstring(ms.encode())
    return {'objects': sum(1 for e in c if local(e) == 'object'),
            'parts': sum(1 for e in c.iter() if local(e) == 'part'),
            'copies': sum(1 for e in m.iter() if local(e) == 'item'),
            'plates': sum(1 for e in c if local(e) == 'plate')}


def check_xml(files, orig, new_names):
    """Every changed XML file parses, and the counts are the old ones plus one of each per new part.
    Returns the problems; the caller refuses to save on any."""
    out = []
    for n, text in files.items():
        if isinstance(text, str) and text != orig.get(n) and n != 'Metadata/project_settings.config':
            try:
                ET.fromstring(text.encode())
            except ET.ParseError as e:
                out.append('%s does not parse: %s' % (n, e))
    if out:
        return out
    before = counts(orig['3D/3dmodel.model'], orig['Metadata/model_settings.config'])
    after = counts(files['3D/3dmodel.model'], files['Metadata/model_settings.config'])
    for k in before:
        if after[k] != before[k] + len(new_names):
            out.append('%d %s, expected %d' % (after[k], k, before[k] + len(new_names)))
    names = [e.get('value') for o in ET.fromstring(files['Metadata/model_settings.config'].encode())
             if local(o) == 'object' for e in o if local(e) == 'metadata' and e.get('key') == 'name']
    out += ['no object named %s' % n for n in new_names if n not in names]
    return out


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    path, stls, down, ok = sys.argv[1], [], {}, ''
    args = iter(sys.argv[2:])
    for a in args:
        if a == '--approved':
            ok = next(args, '')
        elif a == '--down':
            part, _, face = next(args, '').partition('=')
            if face not in DOWN:
                sys.exit('--down: write it as PART=FACE, where FACE is one of %s' % ' '.join(DOWN))
            down[part] = face
        else:
            stls.append(a)
    approved(ok)
    known = part_names(stls)
    for part in down:
        if part not in known:
            sys.exit('--down %s: no part named %s. The parts are: %s' % (part, part, ', '.join(known)))
    full = os.path.abspath(path)
    # Writing under an open project loses the person's newest changes when they save it again. Any
    # running Bambu Studio counts: one they opened the file in has no path in its command line.
    ps = subprocess.run(['ps', '-axwwo', 'pid=,command='], capture_output=True, text=True).stdout
    busy = [l.split()[0] for l in ps.splitlines() if 'BambuStudio.app/Contents/MacOS/BambuStudio' in l]
    if busy:
        sys.exit('Bambu Studio is running (pid %s) and may have %s open. Ask the person to save and quit it first.' % (', '.join(busy), path))
    with zipfile.ZipFile(path) as z:
        order = [i.filename for i in z.infolist()]
        files = {n: z.read(n).decode() if n.endswith(('.model', '.config', '.xml', '.rels')) else z.read(n) for n in order}
    orig = dict(files)
    model, ms = files['3D/3dmodel.model'], files['Metadata/model_settings.config']
    comps = {}  # object id -> its components: (tag, attrs)
    for oid, body in re.findall(r'<object id="(\d+)"[^>]*>\s*<components>(.*?)</components>', model, re.S):
        comps[oid] = [(c, attrs(c)) for c in re.findall(r'<component [^>]*/>', body)]
    items = [(t, attrs(t)) for t in re.findall(r'<item [^>]*/>', model)]
    names = {oid: xml_text(re.search(r'key="name" value="([^"]*)"', body).group(1)) for oid, body in re.findall(r'<object id="(\d+)">(.*?)</object>', ms, re.S)}

    def world(oid, item_m, meshes):
        pts = []
        for tag, a in comps[oid]:
            cm = list(map(float, a.get('transform', IDENTITY).split()))
            pts += [apply(item_m, apply(cm, v)) for v in meshes[a['objectid']]]
        return box(pts)

    def old_meshes(oid):
        return {a['objectid']: mesh_verts(files[a['p:path'].lstrip('/')], a['objectid']) for _, a in comps[oid]}

    # Which parts each STL replaces, by the file name in source_file.
    edits, used = {}, set()  # (object id, part id) -> (stl, offset)
    for oid, body in re.findall(r'<object id="(\d+)">(.*?)</object>', ms, re.S):
        for pid, pbody in re.findall(r'<part id="(\d+)"[^>]*>(.*?)</part>', body, re.S):
            sf = re.search(r'key="source_file" value="([^"]*)"', pbody)
            stl = next((s for s in stls if sf and os.path.basename(xml_text(sf.group(1))) == os.path.basename(s)), None)
            if stl:
                o = [float((re.search(r'key="source_offset_%s" value="([^"]*)"' % k, pbody) or [0, 0])[1]) for k in 'xyz']
                edits[(oid, pid)] = (stl, o)
                used.add(stl)
    # An STL whose mesh is already in the project, at the same place in its own frame, changes nothing.
    matched, objs = set(used), {oid for oid, _ in edits}
    meshes = {s: new_mesh(s) for s in used}
    for (oid, pid), (stl, o) in list(edits.items()):
        a = next(a for _, a in comps[oid] if a['objectid'] == pid)
        old = re.search(r'<object id="%s"[^>]*>\s*<mesh>(.*?)</mesh>' % pid, files[a['p:path'].lstrip('/')], re.S).group(1)
        xml, verts, c, nf = meshes[stl]
        if all(abs(c[k] - o[k]) < 1e-4 for k in range(3)) and same_mesh(mesh_tris(old), mesh_tris(xml)):
            del edits[(oid, pid)]
    used = {stl for stl, _ in edits.values()}
    for s in sorted(matched - used):
        print('unchanged: %s' % os.path.basename(s))
    for oid, name in names.items():
        if oid in comps and oid not in objs:
            print('no STL given, left as is: %s' % name)
    if not edits and not [s for s in stls if s not in matched]:
        print('nothing changed: %s is left as is' % path)
        return
    touched = sorted({oid for oid, _ in edits}, key=int)
    before = {oid: [world(oid, list(map(float, a.get('transform', IDENTITY).split())), old_meshes(oid)) for _, a in items if a['objectid'] == oid] for oid in touched}

    faces = {}
    for (oid, pid), (stl, o) in edits.items():
        xml, verts, c, nf = meshes[stl]
        d = [c[k] - o[k] for k in range(3)]
        tag, a = next((t, a) for t, a in comps[oid] if a['objectid'] == pid)
        fname = a['p:path'].lstrip('/')
        files[fname] = re.sub(r'(<object id="%s"[^>]*>\s*)<mesh>.*?</mesh>' % pid, lambda g: g.group(1) + xml, files[fname], count=1, flags=re.S)
        # The mesh is re-centred on its own outline, so the component moves by the same amount
        # and the part ends up where the old STL put it.
        cm = list(map(float, a.get('transform', IDENTITY).split()))
        cm[9:12] = [cm[9 + k] + apply(cm, d, move=False)[k] for k in range(3)]
        new_tag = re.sub(r'transform="[^"]*"', 'transform="%s"' % fmt(cm), tag) if 'transform=' in tag else tag.replace('/>', ' transform="%s"/>' % fmt(cm))
        model = model.replace(tag, new_tag)
        comps[oid] = [(new_tag, attrs(new_tag)) if t == tag else (t, x) for t, x in comps[oid]]
        faces[(oid, pid)] = (c, d, nf)

    def fix_part(oid):
        def f(g):
            pid, body = g.group(1), g.group(2)
            if (oid, pid) not in faces:
                return g.group(0)
            c, d, nf = faces[(oid, pid)]

            def matrix(m):
                a = list(map(float, m.group(1).split()))
                for k in range(3):
                    a[4 * k + 3] += sum(a[4 * k + j] * d[j] for j in range(3))
                return 'key="matrix" value="%s"' % fmt(a)
            body = re.sub(r'key="matrix" value="([^"]*)"', matrix, body)
            for k, axis in enumerate('xyz'):
                body = re.sub(r'(key="source_offset_%s" value=")[^"]*"' % axis, lambda m: m.group(1) + '%.9g"' % c[k], body)
            body = re.sub(r'(<mesh_stat face_count=")\d+"', lambda m: m.group(1) + '%d"' % nf, body)
            return g.group(0).replace(g.group(2), body)
        return f

    def fix_object(g):
        oid, body = g.group(1), g.group(2)
        if oid not in touched:
            return g.group(0)
        body = re.sub(r'<part id="(\d+)"[^>]*>(.*?)</part>', fix_part(oid), body, flags=re.S)
        # Bambu Studio counts only the model parts here, not modifiers (seen in a project with modifiers).
        total = sum(int(n) for n in re.findall(r'<part id="\d+" subtype="normal_part">.*?<mesh_stat face_count="(\d+)"', body, re.S))
        body = re.sub(r'<metadata face_count="\d+"/>', '<metadata face_count="%d"/>' % total, body, count=1)
        return '<object id="%s">%s</object>' % (oid, body)
    ms = re.sub(r'<object id="(\d+)">(.*?)</object>', fix_object, ms, flags=re.S)

    # Keep each copy's outline centred where it was, with its bottom at the old height.
    bw, bh = bed_size(files['Metadata/project_settings.config'])
    # Which plate each copy is on, to warn when a part grows over its plate's edge.
    plate_of, blocks = {}, re.findall(r'<plate>(.*?)</plate>', ms, re.S)
    for k, body in enumerate(blocks):
        for o, i in re.findall(r'key="object_id" value="(\d+)"/>\s*<metadata key="instance_id" value="(\d+)"', body):
            plate_of[(o, int(i))] = k
    cols0 = math.ceil(math.sqrt(len(blocks) or 1))
    boxes = {}  # (object id, copy) -> its outline on the plate after this run
    for oid in touched:
        copies = [(t, a) for t, a in items if a['objectid'] == oid]
        for n, ((tag, a), (olo, ohi)) in enumerate(zip(copies, before[oid])):
            im = list(map(float, a.get('transform', IDENTITY).split()))
            lo, hi = world(oid, im, {a2['objectid']: meshes[edits[(oid, a2['objectid'])][0]][1] if (oid, a2['objectid']) in edits else old_meshes(oid)[a2['objectid']] for _, a2 in comps[oid]})
            shift = [(olo[0] + ohi[0] - lo[0] - hi[0]) / 2, (olo[1] + ohi[1] - lo[1] - hi[1]) / 2, olo[2] - lo[2]]
            shift = [0 if abs(v) < 1e-6 else v for v in shift]  # float noise when nothing changed
            im[9:12] = [im[9 + k] + shift[k] for k in range(3)]
            new_tag = re.sub(r'transform="[^"]*"', 'transform="%s"' % fmt(im), tag)
            model = model.replace(tag, new_tag)
            size = lambda l, h: 'x'.join('%.1f' % (h[k] - l[k]) for k in range(3))
            print('new mesh: %-18s %s mm -> %s mm' % (names.get(oid, oid), size(olo, ohi), size(lo, hi)))
            lo, hi = [lo[k] + shift[k] for k in range(3)], [hi[k] + shift[k] for k in range(3)]
            boxes[(oid, n)] = (lo, hi)
            k = plate_of.get((oid, n))
            if hi[0] - lo[0] > bw or hi[1] - lo[1] > bh:
                print('WARNING: %s is now bigger than the %.0f x %.0f bed' % (names.get(oid, oid), bw, bh))
            elif k is not None:
                ox, oy = (k % cols0) * bw * GAP, -(k // cols0) * bh * GAP
                if lo[0] < ox - 1e-3 or hi[0] > ox + bw + 1e-3 or lo[1] < oy - 1e-3 or hi[1] > oy + bh + 1e-3:
                    print('WARNING: %s now sticks out over the edge of plate %d. Move it in Bambu Studio'
                          % (names.get(oid, oid), k + 1))

    spacing_check(files['Metadata/project_settings.config'], blocks, plate_of, boxes, items, names, world, old_meshes)

    # New STLs: a new object on a new plate each, laid out like build_3mf.py does.
    ids = [int(i) for t in files.values() if isinstance(t, str) for i in re.findall(r'<object id="(\d+)"', t)]
    nums = [int(n) for n in re.findall(r'3D/Objects/object_(\d+)\.model', ' '.join(files))]
    plates = len(re.findall(r'<plate>', ms))
    new = [s for s in stls if s not in matched]
    cols = math.ceil(math.sqrt(plates + len(new)))
    if new and plates and cols != cols0:
        # The grid gets a new column, so Bambu Studio puts plate 2 onwards somewhere else.
        # Each part moves with its plate, so it keeps its spot on the plate.
        count, moved = {}, set()
        for tag in re.findall(r'<item [^>]*/>', model):
            oid = attrs(tag)['objectid']
            n = count[oid] = count.get(oid, -1) + 1
            k = plate_of.get((oid, n))
            if k is None:
                continue
            dx = (k % cols - k % cols0) * bw * GAP
            dy = -(k // cols - k // cols0) * bh * GAP
            if dx or dy:
                im = list(map(float, attrs(tag).get('transform', IDENTITY).split()))
                im[9:11] = [im[9] + dx, im[10] + dy]
                model = model.replace(tag, re.sub(r'transform="[^"]*"', 'transform="%s"' % fmt(im), tag), 1)
                moved.add(k + 1)
        if moved:
            print('plates now in %d columns: moved plate %s along with its parts' % (cols, ', '.join(map(str, sorted(moved)))))
    ident = max([int(i) for i in re.findall(r'key="identify_id" value="(\d+)"', ms)] or [100])
    template = files['3D/Objects/object_%d.model' % min(nums)]
    for part in down:
        if part not in [os.path.splitext(os.path.basename(s))[0] for s in new]:
            print('--down %s: %s is already in the project and keeps its turn' % (part, part))
    for s in new:
        name = os.path.splitext(os.path.basename(s))[0]
        xml, verts, c, nf = new_mesh(s)
        lo, hi = box(verts)
        mid, wid, num, k = max(ids) + 1, max(ids) + 2, max(nums) + 1, plates
        ids += [mid, wid]
        nums.append(num)
        fname = '3D/Objects/object_%d.model' % num
        files[fname] = re.sub(r'<object id="\d+" p:UUID="[^"]*"([^>]*)>(\s*)<mesh>.*?</mesh>',
                              lambda g: '<object id="%d" p:UUID="%s"%s>%s%s' % (mid, uuid.uuid4(), g.group(1), g.group(2), xml), template, count=1, flags=re.S)
        # The template file can also hold a modifier's mesh. Keep only the new part's object, or the
        # modifier comes along with an id another file already uses.
        files[fname] = re.sub(r'\s*<object id="(\d+)"[^>]*>.*?</object>',
                              lambda g: g.group(0) if g.group(1) == str(mid) else '', files[fname], flags=re.S)
        order.append(fname)
        px, py = bw / 2 + (k % cols) * bw * GAP, bh / 2 - (k // cols) * bh * GAP
        model = model.replace(' </resources>', '  <object id="%d" p:UUID="%s" type="model">\n   <components>\n    <component p:path="/%s" objectid="%d" p:UUID="%s" transform="%s"/>\n   </components>\n  </object>\n </resources>'
                              % (wid, uuid.uuid4(), fname, mid, uuid.uuid4(), fmt([1, 0, 0, 0, 1, 0, 0, 0, 1] + c)), 1)
        # The turn works on the part as drawn (mesh plus c); then its outline is centred and its bottom set on the plate.
        r = DOWN[down.get(name, '-z')]
        q = [tuple((x + c[0]) * r[k] + (y + c[1]) * r[3 + k] + (z + c[2]) * r[6 + k] for k in range(3)) for x, y, z in verts]
        qlo, qhi = box(q)
        model = model.replace(' </build>', '  <item objectid="%d" p:UUID="%s" transform="%s" printable="1"/>\n </build>'
                              % (wid, uuid.uuid4(), fmt(r + [px - (qlo[0] + qhi[0]) / 2, py - (qlo[1] + qhi[1]) / 2, -qlo[2]])), 1)
        lo, hi = qlo, qhi
        rels = files['3D/_rels/3dmodel.model.rels']
        files['3D/_rels/3dmodel.model.rels'] = rels.replace('</Relationships>', ' <Relationship Target="/%s" Id="rel-%d" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>' % (fname, num))
        part = ('  <object id="%d">\n    <metadata key="name" value="%s"/>\n    <metadata key="extruder" value="1"/>\n    <metadata face_count="%d"/>\n'
                '    <part id="%d" subtype="normal_part">\n      <metadata key="name" value="%s"/>\n      <metadata key="matrix" value="%s"/>\n'
                '      <metadata key="source_file" value="%s"/>\n      <metadata key="source_object_id" value="0"/>\n      <metadata key="source_volume_id" value="0"/>\n'
                '      <metadata key="source_offset_x" value="%.9g"/>\n      <metadata key="source_offset_y" value="%.9g"/>\n      <metadata key="source_offset_z" value="%.9g"/>\n'
                '      <mesh_stat face_count="%d" edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n    </part>\n  </object>\n'
                % (wid, xml_attr(name), nf, mid, xml_attr(os.path.basename(s)), fmt([1, 0, 0, c[0], 0, 1, 0, c[1], 0, 0, 1, c[2], 0, 0, 0, 1]),
                   xml_attr(os.path.basename(s)), c[0], c[1], c[2], nf))
        ident += 11
        plate = ('  <plate>\n    <metadata key="plater_id" value="%d"/>\n    <metadata key="plater_name" value="%s"/>\n    <metadata key="locked" value="false"/>\n'
                 '    <metadata key="filament_map_mode" value="Auto For Flush"/>\n    <metadata key="gcode_file" value=""/>\n    <model_instance>\n'
                 '      <metadata key="object_id" value="%d"/>\n      <metadata key="instance_id" value="0"/>\n      <metadata key="identify_id" value="%d"/>\n'
                 '    </model_instance>\n  </plate>\n' % (k + 1, xml_attr(name), wid, ident))
        ms = ms.replace('  <plate>', part + '  <plate>', 1)
        ms = re.sub(r'(?=  <assemble>|</config>)', lambda g: plate, ms, count=1)
        if 'Metadata/cut_information.xml' in files:
            cut = files['Metadata/cut_information.xml']
            n = len(re.findall(r'<object id=', cut)) + 1
            files['Metadata/cut_information.xml'] = cut.replace('</objects>', ' <object id="%d">\n  <cut_id id="0" check_sum="1" connectors_cnt="0"/>\n </object>\n</objects>' % n)
        plates += 1
        print('new part:  %-18s %s mm, plate %d, filament 1, %s down' % (name, 'x'.join('%.1f' % (hi[j] - lo[j]) for j in range(3)), k + 1, down.get(name, '-z')))

    files['3D/3dmodel.model'], files['Metadata/model_settings.config'] = model, ms
    # A name the XML can't hold, or an insertion point that wasn't found (Bambu Studio changed its
    # spacing), leaves a file Bambu Studio can't open. Read it all back before anything is written.
    problems = check_xml(files, orig, [os.path.splitext(os.path.basename(s))[0] for s in new])
    if problems:
        sys.exit('not saved, %s is left as is: the updated project does not read back right:\n  %s'
                 % (path, '\n  '.join(problems)))
    # The backup is taken just before the file changes, and only when it does. It goes in a
    # .backups/ folder next to the project, so it lasts until the person deletes it.
    backups = os.path.join(os.path.dirname(os.path.abspath(path)), '.backups')
    os.makedirs(backups, exist_ok=True)
    stem = os.path.join(backups, '%s-%s' % (os.path.splitext(os.path.basename(path))[0], time.strftime('%Y%m%d-%H%M%S')))
    # Never over an older backup: two updates in one second, or a file of the same name elsewhere.
    backup, n = stem + '.3mf', 1
    while os.path.exists(backup):
        n += 1
        backup = '%s-%d.3mf' % (stem, n)
    shutil.copy2(path, backup)
    tmp = full + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in order:
            z.writestr(n, files[n])
    os.replace(tmp, full)
    print('saved %s (backup: %s)' % (path, backup))


if __name__ == '__main__':
    main()
