# 3D print prep

How to go from a finished design to a Bambu Studio project that is ready to print. This is separate
from [fusion/rules.md](../fusion/rules.md), which covers designing.

## The printer

- The scripts and the settings template are set up for a **Bambu Lab X1 Carbon, 0.4 mm nozzle**,
  sliced in **Bambu Studio** (tested with 2.07).
- The projects so far mix Bambu PLA Matte and Bambu PETG HF.
- **Don't ask what's in the AMS.** Give each different filament the next slot, 1, 2, 3 and on, and
  the person matches them to the real spools in Bambu Studio.

## The job

**First, the person sees the design.** Unless they say otherwise, show them the finished design
(pictures from Fusion) and wait for their OK before any STL, `.3mf` or test-print offer. That holds
after every design change too, not only the first one. Both `.3mf` scripts refuse to run without
`--approved "<their words>"`: their OK on the design as it is now, or their words saying to skip the
look.

1. **Find the printable parts.** Every body that gets printed is a part. Leave out look-only bodies
   (like a stand-in for a bought part) and preview copies (a second copy placed only for the
   picture). Print one of each unique part, and write down how many the person needs of each.
2. **Export each part as its own STL,** named after the part (`frame.stl`), in the project's
   `stl/` folder. One body per STL. Export with the library's `write_stl`, which always uses Fusion's
   High mesh refinement; the code check stops any other way.
3. **Give each part a filament, by its job or its color.** Examples:
   - A part that takes load or heat (a holder, a clip) may want PETG; a show part, matte PLA.
   - A two-color part is two bodies, each with its own filament.
   - Fit-test pieces print in the same filament as the real parts, or the test tells nothing.
   - Before the full print, suggest test prints for what's risky: fits, tolerances, thin or tricky
     features. The person decides whether to design them ([fusion/rules.md § Test prints](../fusion/rules.md#test-prints)).
     When a value isn't known yet, offer a calibration piece: one print that tries several values of
     that parameter side by side.

   Write the choice down in the project README as a small table: part, count, filament, why.
4. **Orient each part for the build plate.** The face that was designed to lie on the plate goes down.
   For a Fusion part that is the face with the 45° build-plate chamfer ([fusion/rules.md](../fusion/rules.md) rule 11).
   This step is optional: sometimes the person says how to turn a part, sometimes they
   turn it in Bambu Studio themselves. Either way, **a turn must be kept between runs**: the update
   below never changes a part's orientation.
   - **A round peg printed lying on its side droops on the bed side.** Give it a flat cut there, at
     a shallow angle, and a base a little narrower than its top. A cut of about 10° and an inset
     of 0.2 mm worked; 45° took too much off.
5. **Build the `.3mf` project** with all parts, their counts, filaments and orientation, then open it
   in Bambu Studio for the person to look at. They send it to the printer themselves. Use the script below.
   - **Group parts onto plates by judgement:** one part per plate, similar parts
     together, or everything on one plate, whatever suits the parts and the print. `build_3mf.py`
     puts one part on each plate; regroup after it when another layout fits better.
   - Name each plate after what's on it.
   - Save it in the project folder, next to `stl/`, named after the project (`<project>.3mf`), with no trademarks in the name ([fusion/rules.md](../fusion/rules.md) rule 9).

## Updating the 3MF after the design changes

The person tunes the project in Bambu Studio: global, part and plate settings, orientation, extra
copies and more. A new design iteration must swap in the new STLs **without losing any of that**.
So after the first build, never rebuild the `.3mf` from scratch. Change only the meshes.

What a Bambu `.3mf` holds (it is a zip):

| File inside | What it holds |
|---|---|
| `3D/Objects/object_N.model` | the mesh of each object (one object can hold several parts, like modifiers) |
| `3D/3dmodel.model` | where each object sits on the plate (a transform per part and per copy) |
| `Metadata/model_settings.config` | object and part names, per-object and per-part settings, the filament (`extruder`), `source_file` (the STL it came from) and `source_offset`, and the plate list: name, locked, which objects are on it |
| `Metadata/project_settings.config` | the global printer, filament and print settings |
| `Metadata/plate_N.png`, `top_N.png` | plate pictures |

The update, step by step:

1. **Quit Bambu Studio** first, as in § Building the 3MF below (it saves on its own). Writing under an open,
   unsaved project loses the person's newest changes.
2. **Back up the old file** before writing: the script copies it to a `.backups/` folder next to
   the project, named with the date and time. The backups stay until the person
   deletes them.
3. **Match each new STL to its parts by `source_file`.** Every copy of that part matches too.
4. **Swap only the mesh** in its `object_N.model`. Keep every transform, setting, filament and plate.
   Use `source_offset` so the new mesh sits where the old one did and doesn't jump on the plate.
5. **A new part** gets its own new plate. **A part that's gone** is only reported; never delete the person's
   objects or plates.
6. Open the result in Bambu Studio and say what changed: which parts got a new mesh, any new
   plate, any part that's gone.

The script: `<kit>/3dprinting/update_3mf.py`. It does steps 2–5; you do 1 and 6.

```
python3 <kit>/3dprinting/update_3mf.py <project>/<p>.3mf --approved "<their words>" [--down new_part=-y] <project>/stl/a.stl <project>/stl/b.stl ...
```

- `--down PART=FACE` turns a **new** part onto that face, like `build_3mf.py`. A part already in the
  project keeps its turn. PART is an STL's name without `.stl`; a name that matches none of the STLs given
  stops it, with the list of names.

- It refuses while any Bambu Studio runs (one the person opened the file in doesn't show the
  file in its command line), and backs the old file up to `.backups/` next to it first (step 2).
- It refuses two STLs with the same file name: parts are matched by file name.
- Before it saves, it reads back every file it changed and checks the part count. On a mismatch it
  stops and leaves the project as it was.
- A changed part keeps the middle of its outline where it was and its bottom on the plate. It
  prints each part's old and new size.
- **Parts on one plate need about 70 mm between them when the plate prints by object.** The
  template prints by object on purpose: the head finishes one
  part before the next, and `extruder_clearance_max_radius` (68 mm) is the room the head needs. The
  script warns when two parts on such a plate are closer, by their outlines. A plate's own print
  order, set in Bambu Studio, wins: a plate that prints by layer can pack its parts close.
- `build_3mf.py` refuses to overwrite an existing `.3mf`, so a rebuild can't happen by accident.
- **`open -a BambuStudio <file>` starts a new window every time.** Once, three were left
  open on the same file. Before opening it, check `pgrep -fl BambuStudio`. If it's already
  open, ask to quit it, as in § Building the 3MF.

## Getting the 3MF ready to publish

Plates are grouped by judgement, as in step 5 of § The job.

- **Keep the person's own plates.** Ask which ones they tuned for their printing, and leave those
  as they are.
- **Drop the calibration and test pieces** they no longer need, unless they want one kept.
- **Supports only on the parts that need them.** Turn them off on every other part, so a stranger's
  print doesn't fill with them.
- **A by-object plate keeps its parts 70 mm apart** (§ Updating, the spacing rule).
- Restructure with a one-off script on the zip, after the backup, like the update script; then open
  it for the person to check.

## The settings template

`<kit>/3dprinting/template_3mf/` holds the printer, print and filament settings, with no parts: every
new project starts from it. It is a `.3mf` unpacked, its files without the zip around them, so the
kit holds no binary file (a plugin directory sends any release with a binary file, other than
images and fonts, to a person for review). Made from a tuned project: 0.2 mm layers, 2 walls, 5 top and
3 bottom layers, auto brim; filament 1 Bambu PLA Basic, filament 2 Bambu PETG HF. That project
had PETG HF in both, so slot 1 was copied from another project's PLA Basic slot. Never change a
project's own filaments to make the template. Per-part settings (a brim on one part, no supports on another) stay in their own
project.

- **When the person tunes settings they want kept,** remake it from that project once they have
  saved and quit Bambu Studio:
  `python3 <kit>/3dprinting/make_template.py <project>/<p>.3mf`
  If that project's slot 1 isn't PLA Basic, add
  `--filament "1=OTHER.3mf:1"`, where filament 1 of `OTHER.3mf` is PLA Basic.
  It prints how many settings changed and any it couldn't copy.
- **To look at it in Bambu Studio,** pack it into one file:
  `python3 <kit>/3dprinting/make_template.py <kit>/3dprinting/template_3mf template.3mf`.
  Bambu Studio's command line refuses a project with no parts ("file is empty"); it is a settings
  source for `build_3mf.py`.

## Building the 3MF from the command line

**Do it all in the background: no screen control.** Build and edit the `.3mf`
from the shell, then `open -a BambuStudio <file>` once at the end so the person can look. Don't take
screenshots of Bambu Studio or click in it to check; read the files inside the zip instead.

**When Bambu Studio is in the way, ask, then quit it yourself.** That covers a `.3mf` edit, which needs it quit, and Bambu
sitting on top of Fusion during a build. Check with `pgrep -l -i bambu`. Ask in one line, and on a
yes run `osascript -e 'with timeout of 10 seconds' -e 'quit app "BambuStudio"' -e 'end timeout'`
(without the timeout it hangs for 2 minutes). Don't ask the person to quit it.

**If Bambu Studio is set to save on its own,** don't ask whether to save; just ask to quit it. After the quit, check with `pgrep` that it's gone.
If it's still running, something is waiting on the person: look with a screenshot and tell them what's on
screen. Don't click it. Once, its save prompt could not be clicked anyway: the prompt is a
separate process, and the screen tool refuses clicks on it with a Bambu Studio grant ("belongs to a
different process"). System Events lists no windows or buttons for Bambu Studio either. A timed-out
quit doesn't always mean a prompt: that day it was on its home page with no project open, and a
second quit worked.

The script: `<kit>/3dprinting/build_3mf.py`.

```
python3 <kit>/3dprinting/build_3mf.py <project>/<p>.3mf --approved "<their words>" --down arch_frame=-y <project>/stl/a.stl <project>/stl/b.stl ...
```

Settings come from the template folder (above). `--settings-from OTHER.3mf` takes them from another
project instead.

What it does, and why:

1. Runs Bambu Studio's command line (`--export-3mf`, `--arrange 1`) to turn the STLs into objects.
   It puts them all on **one plate**, even with `--allow-multicolor-oneplate` left off.
2. Its system presets (`--load-settings` with the X1C machine, process and filament `.json` files)
   **don't pull in their parent presets**. The result had a 200 × 200 mm bed, 100 mm height and
   the wrong start G-code. So the script throws those settings away and copies
   `Metadata/project_settings.config` from the template, or from `--settings-from`. Every part
   uses filament 1.
3. Edits the files inside the zip: one `<plate>` per part in `Metadata/model_settings.config`, named
   after the part, and each part's `transform` in `3D/3dmodel.model` moved to the middle of its
   plate. Plates sit one bed plus a fifth apart, in rows of ⌈√n⌉, as Bambu Studio lays them out.
4. `--down PART=FACE` turns a part so that face lies on the plate (step 4 of the job above).

Only plate 1 gets pictures from the command line; Bambu Studio draws the rest when it opens.

Tests: [3mf-test-scenarios.md](3mf-test-scenarios.md), the plan for testing
`build_3mf.py` and `update_3mf.py`.

## Open questions

- Does the plate picture in the `.3mf` need redrawing after a mesh swap, or does Bambu Studio redo it
  on open?
