"""Build a Bambu Studio .3mf from STLs: one plate per part, print settings from one of the person's own projects.

Runs with no screen control: Bambu Studio's command line makes the meshes, then the files inside
the .3mf (a zip) are edited directly. See 3dprinting/rules.md.

Usage (from the repo root):
  python3 projects/hobby/cad-apprentice/3dprinting/build_3mf.py OUT.3mf --approved "<their words>" [--settings-from REF.3mf] [--down PART=-y ...] a.stl b.stl ...

--approved       the person's OK on the design as it is now, in their words ("Looks good"), or their
                 words saying to skip that ("no need to show me"). Required: they see the design
                 before any .3mf (3dprinting/rules.md).

--settings-from  a .3mf whose printer, print and filament settings get copied, or a folder holding
                 one unpacked. Default: the template, the folder 3dprinting/template_3mf/
                 (make_template.py). Every part uses filament 1.
--down PART=FACE the face of PART that goes on the plate: -z (the default, as drawn), +z, -x, +x, -y or +y.
Parts are named after their STL files, and each plate after its part.
"""
import argparse, os, re, shutil, subprocess, sys, tempfile, zipfile
from xml.sax.saxutils import escape, unescape

BAMBU = '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'
PROFILES = '/Applications/BambuStudio.app/Contents/Resources/profiles/BBL'
# Only so the command line runs. Its presets don't resolve their parents (a 200 mm bed, the wrong
# start G-code), so the settings are replaced from --settings-from afterwards.
MACHINE = PROFILES + '/machine/Bambu Lab X1 Carbon 0.4 nozzle.json'
PROCESS = PROFILES + '/process/0.20mm Standard @BBL X1C.json'
FILAMENT = PROFILES + '/filament/Bambu PLA Matte @BBL X1C.json'
# Rows of a 3MF matrix (a point times it) that turn the named face down onto the plate.
DOWN = {
    '-z': [1, 0, 0, 0, 1, 0, 0, 0, 1],
    '-y': [1, 0, 0, 0, 0, 1, 0, -1, 0],
    '+y': [1, 0, 0, 0, 0, -1, 0, 1, 0],
    '-x': [0, 0, 1, 0, 1, 0, -1, 0, 0],
    '+x': [0, 0, -1, 0, 1, 0, 1, 0, 0],
    '+z': [1, 0, 0, 0, -1, 0, 0, 0, -1],
}
GAP = 1.2  # Bambu Studio lays plates out one bed plus a fifth apart.
# A name in an XML attribute: & < > and " written as entities, and read back.
QUOTE = {'"': '&quot;'}


def xml_attr(text):
    return escape(text, QUOTE)


def xml_text(value):
    return unescape(value, {'&quot;': '"', '&apos;': "'"})


def bed_size(settings):
    xs, ys = zip(*(map(float, p.split('x')) for p in re.search(r'"printable_area":\s*\[([^\]]*)\]', settings).group(1).replace('"', '').split(',')))
    return max(xs), max(ys)


def read_settings(ref):
    """The global settings of a Bambu Studio project, checked before anything runs."""
    try:
        if os.path.isdir(ref):
            path = os.path.join(ref, 'Metadata', 'project_settings.config')
            if not os.path.isfile(path):
                raise KeyError(path)
            settings = open(path, 'rb').read().decode()
        else:
            with zipfile.ZipFile(ref) as z:
                settings = z.read('Metadata/project_settings.config').decode()
    except OSError as e:
        sys.exit('--settings-from %s: %s' % (ref, e.strerror or e))
    except zipfile.BadZipFile:
        sys.exit('--settings-from %s is not a .3mf (it is not a zip file)' % ref)
    except KeyError:
        sys.exit('--settings-from %s has no Metadata/project_settings.config, so it is not a Bambu Studio '
                 'project and has no settings to copy' % ref)
    if not re.search(r'"printable_area":\s*\[', settings):
        sys.exit('--settings-from %s: its settings have no printable_area (bed size)' % ref)
    return settings


def approved(words):
    # The person sees the design and says OK before any .3mf, after every design change too. Their
    # words go in the output.
    if not words.strip():
        sys.exit('no --approved: show the person the design (pictures from Fusion) and wait for their OK first. Then pass '
                 'their words: --approved "Looks good" (3dprinting/rules.md § The job)')
    print('approved: %s' % words.strip())


def part_names(stls):
    """Each STL's part name, its file name without .stl. Parts and plates are named after their files,
    so two files with one name would collide."""
    order = [os.path.splitext(os.path.basename(s))[0] for s in stls]
    for i, part in enumerate(order):
        if part in order[:i]:
            sys.exit('two STLs are both named %s: %s and %s. Rename one, since parts are named after their files'
                     % (os.path.basename(stls[i]), stls[order.index(part)], stls[i]))
    return order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('stls', nargs='+')
    ap.add_argument('--settings-from', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template_3mf'))
    ap.add_argument('--down', action='append', default=[])
    ap.add_argument('--approved', default='')
    a = ap.parse_args()
    approved(a.approved)
    # The person tunes the project in Bambu Studio after the first build, so a rebuild would wipe that.
    # Later rounds swap only the meshes (3dprinting/rules.md).
    if os.path.exists(a.out):
        sys.exit('%s exists: update its meshes instead of rebuilding it' % a.out)
    down = {}
    for d in a.down:
        part, eq, face = d.partition('=')
        if not eq or face not in DOWN:
            sys.exit('--down %s: write it as PART=FACE, where FACE is one of -z +z -x +x -y +y' % d)
        down[part] = face
    order = part_names(a.stls)
    for part in down:
        if part not in order:
            sys.exit('--down %s: no part named %s. The parts are: %s' % (part, part, ', '.join(order)))
    settings = read_settings(a.settings_from)
    work = tempfile.mkdtemp()
    try:
        build(a, order, down, settings, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def bambu_lines(text, n=10):
    """The last lines of Bambu Studio's output that say something: no trace, debug or info lines."""
    out = []
    for line in text.splitlines():
        m = re.match(r'\[[^\]]*\] \[0x[0-9a-f]+\] \[(\w+)\]\s*(.*)', line)
        if m:
            if m.group(1) in ('trace', 'debug', 'info'):
                continue
            line = m.group(2)
        if line.strip():
            out.append('  ' + line.strip())
    return out[-n:]


def build(a, order, down, settings, work):
    raw = os.path.join(work, 'raw.3mf')
    cmd = [BAMBU, '--load-settings', MACHINE + ';' + PROCESS, '--load-filaments', FILAMENT,
           '--load-filament-ids', ','.join('1' for _ in a.stls), '--arrange', '1', '--export-3mf', raw] + [os.path.abspath(s) for s in a.stls]
    p = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(raw):
        sys.exit('Bambu Studio\'s command line failed (exit %d), nothing written. Its last lines:\n%s'
                 % (p.returncode, '\n'.join(bambu_lines(p.stdout + '\n' + p.stderr)) or '  (none)'))
    src = zipfile.ZipFile(raw)
    files = {i.filename: src.read(i.filename) for i in src.infolist()}
    files['Metadata/project_settings.config'] = settings.encode()
    bw, bh = bed_size(settings)
    cols = max(1, round(len(order) ** 0.5) + (1 if len(order) ** 0.5 > round(len(order) ** 0.5) else 0))

    m = files['3D/3dmodel.model'].decode()
    ms = files['Metadata/model_settings.config'].decode()
    names = {xml_text(n).replace('.stl', ''): oid for oid, n in re.findall(r'<object id="(\d+)">\s*<metadata key="name" value="([^"]+)"', ms)}
    pts = {}
    for oid, path, t in re.findall(r'<object id="(\d+)".*?p:path="([^"]+)".*?transform="([^"]+)"', m, re.S):
        t = list(map(float, t.split()))
        mesh = files[path.lstrip('/')].decode()
        # The whole transform, turn included: a point times its 4 x 3 matrix.
        pts[oid] = [tuple(x * t[k] + y * t[3 + k] + z * t[6 + k] + t[9 + k] for k in range(3))
                    for x, y, z in ((float(x), float(y), float(z)) for x, y, z in re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', mesh))]
    plates = []
    new_id = max([int(v) for v in re.findall(r'<metadata key="identify_id" value="(\d+)"/>', ms)] or [0])
    for i, part in enumerate(order):
        oid = names[part]
        r = DOWN[down.get(part, '-z')]
        q = [(x * r[0] + y * r[3] + z * r[6], x * r[1] + y * r[4] + z * r[7], x * r[2] + y * r[5] + z * r[8]) for x, y, z in pts[oid]]
        lo = [min(p[k] for p in q) for k in range(3)]
        hi = [max(p[k] for p in q) for k in range(3)]
        if hi[0] - lo[0] > bw or hi[1] - lo[1] > bh:
            print('WARNING: %s is %.0f x %.0f mm, bigger than the %.0f x %.0f bed' % (part, hi[0] - lo[0], hi[1] - lo[1], bw, bh))
        cx, cy = bw / 2 + (i % cols) * bw * GAP, bh / 2 - (i // cols) * bh * GAP
        tr = [cx - (lo[0] + hi[0]) / 2, cy - (lo[1] + hi[1]) / 2, -lo[2]]
        m = re.sub(r'(<item objectid="%s" [^>]*transform=")[^"]+"' % oid, lambda g: g.group(1) + ' '.join('%g' % v for v in r + tr) + '"', m)
        found = re.search(r'<model_instance>\s*<metadata key="object_id" value="%s"/>.*?</model_instance>' % oid, ms, re.S)
        if found:
            inst = found.group(0)
        else:
            # Bambu Studio's --arrange leaves a part bigger than the bed off every plate. Put it on its own.
            new_id += 1
            inst = ('<model_instance>\n      <metadata key="object_id" value="%s"/>\n      <metadata key="instance_id" value="0"/>\n'
                    '      <metadata key="identify_id" value="%d"/>\n    </model_instance>' % (oid, new_id))
        # Only plate 1 has pictures from the command line; Bambu Studio draws the rest.
        thumbs = '' if i else ''.join('    <metadata key="%s" value="Metadata/%s"/>\n' % kv for kv in (
            ('thumbnail_file', 'plate_1.png'), ('thumbnail_no_light_file', 'plate_no_light_1.png'), ('top_file', 'top_1.png'), ('pick_file', 'pick_1.png')))
        plates.append('  <plate>\n    <metadata key="plater_id" value="%d"/>\n    <metadata key="plater_name" value="%s"/>\n'
                      '    <metadata key="locked" value="false"/>\n    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
                      '    <metadata key="gcode_file" value=""/>\n%s    %s\n  </plate>\n' % (i + 1, xml_attr(part), thumbs, inst))
        print('plate %d: %-18s %.1f x %.1f x %.1f mm, %s down' % (i + 1, part, hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], down.get(part, '-z')))
    ms = re.sub(r'  <plate>.*?</plate>\n', lambda g: ''.join(plates), ms, count=1, flags=re.S)
    ms = re.sub(r'value="([^"]+)\.stl"(?=/>\s*<metadata key="extruder")', r'value="\1"', ms)
    files['3D/3dmodel.model'] = m.encode()
    files['Metadata/model_settings.config'] = ms.encode()
    # Write next to the target, then link it in: a crash leaves no half-written .3mf, and a file that
    # appeared since the check in main() is never overwritten.
    fd, tmp = tempfile.mkstemp(suffix='.3mf.tmp', dir=os.path.dirname(os.path.abspath(a.out)))
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            for i in src.infolist():
                z.writestr(i.filename, files[i.filename])
        os.link(tmp, a.out)
    except FileExistsError:
        sys.exit('%s exists: update its meshes instead of rebuilding it' % a.out)
    finally:
        os.remove(tmp)
    print('saved', a.out)


if __name__ == '__main__':
    main()
