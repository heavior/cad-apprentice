"""Make the empty Bambu Studio template project from one of the person's tuned projects.

The person tunes the printer, print and filament settings in a project, then wants them as the start
of every new one. The template keeps only the global settings, one empty plate and
no parts, so per-part settings (a brim on one part, no supports on another) don't carry over.
build_3mf.py takes its settings from the template unless --settings-from names another project.

Usage (from the repo root):
  python3 projects/hobby/cad-apprentice/3dprinting/make_template.py projects/hobby/<p>/<p>.3mf [OUT.3mf] [--filament N=OTHER.3mf:M ...]
OUT defaults to 3dprinting/template.3mf. --filament puts filament M of OTHER.3mf into slot N
(both counted from 1), for when FROM has the wrong filament there. Filament 1 is Bambu PLA Basic.
"""
import json, os, re, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, 'template.3mf')
# The model file Bambu Studio writes, with no objects in it.
EMPTY = '<resources>\n </resources>\n <build/>'
PLATE = ('<config>\n  <plate>\n    <metadata key="plater_id" value="1"/>\n    <metadata key="plater_name" value=""/>\n'
         '    <metadata key="locked" value="false"/>\n    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
         '    <metadata key="gcode_file" value=""/>\n  </plate>\n</config>\n')
# Per-filament values that belong to the slot, not the filament: the spool colour and the nozzle it
# feeds. A swapped filament keeps them.
SLOT_KEYS = {'filament_colour', 'filament_multi_colour', 'filament_colour_type', 'default_filament_colour',
             'filament_nozzle_map', 'filament_map', 'filament_self_index', 'filament_volume_map'}


def swap_filament(cfg, n, other, m):
    """Puts filament m of the other project's settings into slot n. Lists are one value per filament,
    or a fixed number per filament (two for X1C nozzle variants)."""
    count, other_count = len(cfg['filament_settings_id']), len(other['filament_settings_id'])
    if not (1 <= n <= count and 1 <= m <= other_count):
        sys.exit('--filament %d=...:%d: this project has %d filaments, the other %d' % (n, m, count, other_count))
    changed, skipped = [], []
    for k, v in cfg.items():
        o = other.get(k)
        if k in SLOT_KEYS or not isinstance(v, list) or not v or not isinstance(o, list) or not o:
            continue
        if len(v) % count or len(o) % other_count or len(v) // count != len(o) // other_count:
            if k.startswith('filament_') and len(v) != len(o):
                skipped.append(k)  # Looks like a filament value but doesn't line up: say so.
            continue
        w = len(v) // count
        new = o[(m - 1) * w:m * w]
        if v[(n - 1) * w:n * w] != new:
            v[(n - 1) * w:n * w] = new
            changed.append(k)
    # One entry for the process, one per filament, one for the printer.
    d, od = cfg.get('different_settings_to_system'), other.get('different_settings_to_system')
    if d and od and len(d) == count + 2 and len(od) == other_count + 2:
        d[n] = od[m]
    else:
        skipped.append('different_settings_to_system')
    return changed, skipped


def main():
    args, swaps = sys.argv[1:], []
    while '--filament' in args:
        i = args.index('--filament')
        m = re.fullmatch(r'(\d+)=(.+):(\d+)', args[i + 1] if i + 1 < len(args) else '')
        if not m:
            sys.exit(__doc__)
        swaps.append((int(m.group(1)), m.group(2), int(m.group(3))))
        del args[i:i + 2]
    if len(args) not in (1, 2):
        sys.exit(__doc__)
    src, out = args[0], args[1] if len(args) == 2 else TEMPLATE
    # Settings the person changed but hasn't saved are not in the file yet.
    if subprocess.run(['pgrep', '-f', 'BambuStudio.app/Contents/MacOS/BambuStudio'], capture_output=True).returncode == 0:
        print('note: Bambu Studio is running; unsaved changes are not in %s' % src)
    z = zipfile.ZipFile(src)
    model = z.read('3D/3dmodel.model').decode()
    model = re.sub(r'<resources>.*</build>', EMPTY, model, flags=re.S)
    model = re.sub(r'\s*<metadata name="Thumbnail_\w+">[^<]*</metadata>', '', model)
    rels = re.sub(r'\s*<Relationship [^>]*Target="/Metadata/[^"]*"[^>]*/>', '', z.read('_rels/.rels').decode())
    files = {
        '[Content_Types].xml': z.read('[Content_Types].xml'),
        '_rels/.rels': rels.encode(),
        '3D/3dmodel.model': model.encode(),
        'Metadata/project_settings.config': settings(z.read('Metadata/project_settings.config'), swaps),
        'Metadata/model_settings.config': ('<?xml version="1.0" encoding="UTF-8"?>\n' + PLATE).encode(),
    }
    if 'Metadata/slice_info.config' in z.namelist():
        files['Metadata/slice_info.config'] = z.read('Metadata/slice_info.config')
    z.close()  # OUT may be FROM: all read before writing.
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as w:
        for n, data in files.items():
            w.writestr(n, data)
    print('saved %s: settings from %s, one empty plate, no parts' % (out, src))


def settings(raw, swaps):
    if not swaps:
        return raw
    cfg = json.loads(raw)
    for n, other_path, m in swaps:
        other = json.loads(zipfile.ZipFile(other_path).read('Metadata/project_settings.config'))
        changed, skipped = swap_filament(cfg, n, other, m)
        print('filament %d is now %s from %s (filament %d): %d settings changed'
              % (n, cfg['filament_settings_id'][n - 1], other_path, m, len(changed)))
        if skipped:
            print('  not copied, they don\'t line up: %s' % ', '.join(skipped))
    return (json.dumps(cfg, indent=4, ensure_ascii=False) + '\n').encode()


if __name__ == '__main__':
    main()
