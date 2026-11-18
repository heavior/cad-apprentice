# 3MF scripts: test plan

What the automatic tests for the 3MF scripts must cover, written as plain scenarios. Built
in the same overnight session as the
[cad_apprentice test plan](../fusion/tests/upsert-test-scenarios.md). How the scripts are
meant to work is in [3dprinting/rules.md](rules.md).

The scripts:
- **`build_3mf.py`** (this folder): STLs in, a Bambu Studio project out, one plate per part,
  settings copied from one of the person's projects. Exists.
- **`update_3mf.py`** (this folder): swaps new meshes into a project the person has tuned,
  keeping everything else (3dprinting/rules.md § Updating the 3MF). Built after this plan was
  written, so group U tests it as it is; it isn't rewritten.
- **The STL export** in a design's build script. Here it only matters as the input to
  `build_3mf.py`.

## 1. How the tests run

- **No Fusion, no screen.** Plain Python (stdlib `unittest`) plus Bambu Studio's command line,
  the way `build_3mf.py` already runs. Nothing is opened in Bambu Studio, and no screenshots are
  taken (3dprinting/rules.md: do it all in the background). So these tests can run any time, not
  only at night.
- **Test files, made by the test.** Small STLs written by the test itself, binary and ASCII:
  - a 20 mm cube
  - an L-shaped block with one big flat face, so it is clear which face is down
  - a long bar bigger than the bed
  - a part with a hole and an overhang
  - two STLs with the same file name in different folders
  - a broken STL (open mesh, or an empty file)
- **Reference settings.** The default, the folder `<kit>/3dprinting/template_3mf/`,
  as the docs say. Tests that need it as one file use `tests/run/template.3mf`, which
  `make_template.py` packs from the folder. B11 also uses a copy of your own `.3mf` with other
  printer settings, named by the `B11_REF_3MF` environment variable; if it is unset or missing,
  that part of B11 is skipped and listed, not failed.
- **Where it writes.** Only in `<kit>/3dprinting/tests/run/`. Never in a project
  folder. `build_3mf.py` makes a temp work folder, so every test runs the scripts with `TMPDIR` set to
  `run/tmp/`. `update_3mf.py` backs up into `.backups/` next to the project, which in a test is
  inside `run/`. A check at the
  start and the end of the run: every `.3mf` under the `CAD_PROJECTS` folder (your design projects) is byte for byte the same as at the
  start. The tests' own
  `run/` folder is left out of it. A file the person saved during the run shows up here too.
- **How a result is read.** Every check opens the output `.3mf` as a zip and reads the XML and mesh
  files inside, as the scripts do. A helper turns a project into a plain summary:
  - plates, with names and which objects are on each
  - each object's name, filament, `source_file`, and transform
  - each object's mesh after its transform: size, volume, lowest point, and the area of triangles
    lying on z = 0
  - the global settings file

  Most checks compare two summaries.
- **Bambu Studio quit, and the U group alone.** `update_3mf.py` refuses to run while any process's
  command line holds `BambuStudio.app/Contents/MacOS/BambuStudio`. The person's own window counts,
  and so does the command line that B tests start. So they quit Bambu Studio before the night,
  and the U
  tests never run while a B test is running.
- **Slicing as the final check.** Try Bambu Studio's command line to slice every plate of an output
  (`--slice 0`, with output to the test folder). If it slices with no error and no warning about
  parts off the bed or floating, the project is printable. First check that the command line
  supports this on the installed Bambu Studio version; if it doesn't, mark these checks skipped and say so in
  the report. Never send anything to the printer.

## 2. Checks after every build

1. **One plate per part,** in the order the STLs were given, each named after its STL file without
   `.stl`.
2. **Each part sits on its own plate:** centred in that plate's bed, lowest point at z = 0, and
   inside the bed, unless it is bigger than the bed (then a warning was printed).
3. **Mesh kept:** each part's volume and size match its STL (turned, if `--down` was given), within
   0.01 mm and 0.1 % volume.
4. **Settings copied:** `Metadata/project_settings.config` is byte for byte the reference's.
5. **Filament:** every part uses filament 1 (today's rule).
6. **Names:** object names have no `.stl`; plate names match the parts.
7. **Opens:** the zip is valid, and every file that `[Content_Types].xml` and the `_rels` files name
   is there.
8. **Slices** (if supported, see § 1).
9. **Nothing else touched:** the project-files check in § 1.

## 3. Scenarios

**(gap)** marks behavior seen in the code that the plan wants changed. Those run first.

### B. `build_3mf.py`: building a project
- **B1** One STL: one plate, the part in its middle.
- **B2** Six STLs: six plates in rows of 3, one bed plus a fifth apart, the way
  Bambu Studio lays them out.
- **B3** 1, 2, 3, 4, 5, 7, 9 and 10 STLs: rows of ⌈√n⌉ every time.
- **B4** Each `--down` face (`-z`, `+z`, `-x`, `+x`, `-y`, `+y`) on the L-block: the face named
  is the one at z = 0 (its triangle area there matches the face's area), and the volume is
  unchanged.
- **B5** `--down` on one part of several: only that part turns.
- **B6** A part bigger than the bed: a warning naming the part and both sizes, and the file is still
  written.
- **B7** The output file already exists: the script stops with its message and the file is
  untouched (byte for byte). This is what protects the person's tuned projects. Already in the code; kept as
  a regression test.
- **B8** A part with a hole and an overhang: the mesh survives unchanged (no faces lost or merged).
- **B9** Binary and ASCII STLs both work.
- **B10** STL paths with spaces and non-ASCII letters (real folders often have both).
- **B11** Reference settings from a different printer setup (if you have one among your own `.3mf`
  files): copied as is, and the bed size used for the plates is that project's.
- **B12** Running it twice into two new files gives the same plates, transforms and meshes.
- **B13** **(gap)** `--down` naming a part that isn't in the list is ignored with no message.
  Expected: a clear error naming the part.
- **B14** **(gap)** A face that doesn't exist (`--down part=-q`): today a Python `KeyError`. And
  `--down part` with no `=`: today a `ValueError`. Expected: a clear error listing the six faces.
- **B15** **(gap)** Two STLs with the same file name from different folders: their objects collide
  by name. Expected: a clear error before Bambu Studio runs.
- **B16** **(gap)** Bambu Studio's command line fails (a broken or empty STL): today its output is
  thrown away, the error says only that the command failed, and the temp folder stays behind.
  Expected: Bambu Studio's last lines in the error, and the temp folder removed.
- **B17** **(gap)** The object offset is read, but not any turn Bambu Studio's command line puts in
  an object's transform. `--arrange 1` is always on; check whether it ever turns a part (a long
  bar is the likely case); if so, sizes and centres come out wrong. Expected: the full transform is used.
- **B18** **(gap)** Every part gets filament 1, but the job (3dprinting/rules.md step 3) gives
  each part a filament. Expected: an option like `--filament PART=N`, with filament N taken from
  the reference project. Writing the option is a new feature: build it only if the person said yes (§ 5).
- **B19** **(gap)** A reference `.3mf` with no `project_settings.config` (a plain 3MF from another
  program): today a `KeyError` after Bambu Studio has already run, and the temp folder stays.
  Expected: the reference is checked first, a clear error, nothing written.
- **B20** Plate pictures: only plate 1 has them, and Bambu Studio's slice (§ 1) doesn't complain
  about the missing ones.
- **B21** No `--approved`, or a blank one: a clear error naming the flag, before Bambu Studio runs,
  nothing written (the person sees the design before any `.3mf`).
- **B22** Parts named `a&b` and `c<d"e>`: the project's XML reads back, and the plates carry those
  names.
- **B23** The `.3mf` is written to a temp file next to it and linked in, so a crash leaves no
  half-written project and a file that appeared meanwhile is never overwritten: no `.tmp` is left.

### U. `update_3mf.py`: new meshes into a tuned project
Runs alone, with Bambu Studio quit (§ 1).

Each scenario starts from a project made by `build_3mf.py`, then "tuned" by the test the way a person
would in Bambu Studio: a changed global setting, a per-object setting (infill), a part turned and
moved, a second copy of one part, two parts packed onto one plate, a renamed plate, a locked plate,
a filament change, and a modifier inside one object. Then the STLs change and the update runs.

- **U1** One STL changes: only that object's mesh changes. Every setting, transform, copy, plate,
  name and filament stays, compared field by field with the tuned project.
- **U2** A changed part keeps its spot: it doesn't jump on the plate (`source_offset`).
- **U3** A part with two copies: both get the new mesh.
- **U4** A part that got bigger and no longer fits its plate: a warning, nothing moved.
- **U5** A new STL: a new plate named after it, nothing else moved.
  *Read in the run:* when the new plate gives the grid a new column (4 plates to 5),
  Bambu Studio puts plate 3 onwards somewhere else. So "nothing moved" means each part keeps its
  spot on its own plate. The test checks that, and the script now moves parts with their plate.
- **U6** An STL that's gone: reported. Its object and plate stay.
- **U7** No STL changed: the file is byte for byte the same, and the run says nothing changed.
- **U8** Matching by `source_file`, not by name: a part renamed in Bambu Studio still updates.
- **U9** The modifier inside an object is kept when the object's main mesh changes.
- **U10** A backup is written to `.backups/` next to the project before the file is changed, and
  putting the backup back gives the original byte for byte.
- **U11** Bambu Studio is running: the update stops and asks the person to save and quit it first. The
  script checks the process list, not file locks, so the stand-in is a copy of `/bin/sleep` at
  `run/tmp/BambuStudio.app/Contents/MacOS/BambuStudio`, started for the test and stopped after.
  *Changed in the run:* macOS kills a copy of `/bin/sleep` at that path as soon as it
  starts (exit 137). So the test starts `/bin/sleep` itself under that path name instead. Its
  command line holds the path all the same, which is what the script checks.
- **U12** The result slices (§ 1), and the update of the update (U1 run twice) changes nothing.
- **U13** Spacing when a plate prints by object (the template prints by object on
  purpose). It prints one part to the top before the next, so parts on one plate need the
  head's clearance between them (`extruder_clearance_max_radius`, 68 mm). alpha grows from its
  middle towards delta, which shares plate 1:
  a) alpha 70 mm: a warning naming plate 1, alpha and delta renamed. Nothing moved.
  b) alpha 40 mm, more than 68 mm away: no warning.
  c) alpha 70 mm, but plate 1 set to print by layer (Bambu Studio's per-plate order, the way the
  bridge's plate 1 is): no warning, since a plate's own order wins.
- **U14** No `--approved`: a clear error naming the flag, and the file is byte for byte the same.
- **U15** `--down`: a new part `epsilon=+x` lies on its +x face, and `beta=-y`, a part already in
  the project, keeps its turn with a note saying so. `ghost=-y`, a name with no STL, stops it with
  the list of parts, and the file is byte for byte the same.
- **U16** New parts named `a&b` and `c<d"e>`: the project's XML reads back with those names. Then
  `a&b` changes and is updated in place, found by its file name, not added again.
- **U17** Two STLs named `gamma.stl` in different folders: a clear error, and the file is byte for
  byte the same.
- **U18** The modifier's mesh sits in the lowest-numbered object file, which new parts are built
  from. A new part is added: its file holds only its own object, no object id is used twice,
  alpha keeps its modifier, and the project slices.

### T. `make_template.py`: the template's filaments
- **T1** `--filament 1=OTHER.3mf:1` copies one filament slot's settings from another project: every
  `filament_*` setting of slot 1 changes to the other project's, slot 2 and every non-filament
  setting stay, the slot's colour stays, and `print_sequence` is still "by object". Done by hand
  once to make slot 1 PLA Basic, copied from another project: 38 settings changed, 3 empty mixed-filament fields not copied. No automated test yet.

## 4. Order

1. The summary helper and the § 2 checks, proved on B1.
2. The **(gap)** scenarios B13–B17 and B19. Fix each in `build_3mf.py`, one commit per ID. B18
   is skipped (§ 5).
3. The rest of B.
4. The U group, alone (§ 1). With Bambu Studio open they can't run, and each is listed as a
   skip, "Bambu Studio is open". A failure is fixed in `update_3mf.py`, one commit per ID.
5. Results in `<kit>/3dprinting/tests/run/results/`, and a short section in the night's morning
   report.

These need no Fusion, so in the overnight session they run while Fusion is busy, or first, if
the Fusion runner isn't ready. One at a time: B, then U.

## 5. Permissions and questions

Asked at the start of the night, in one list with the
[cad_apprentice plan's](../fusion/tests/upsert-test-scenarios.md) § 6, which repeats the
must-ask ones.

**Permissions:**

| What | Why |
|---|---|
| Run `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio` from the shell (export and slice) | Building and slicing test projects. No window, no printer |
| `python3` on the tests, `build_3mf.py` and `update_3mf.py` | Running them |
| Edit `build_3mf.py` and `update_3mf.py`; create the tests in `scripts/print/` | Fixes and tests |
| Read the `.3mf` that `B11_REF_3MF` names and copy it into the test folder | B11 |
| `mkdir`, `cp`, `rm` in `<kit>/3dprinting/tests/run/` only, and a stand-in `sleep` there (U11) | Test output |

**Questions:**

| Question | Default |
|---|---|
| B18: add a filament per part (`--filament PART=N`)? | No, skipped |
| Which project is the reference for settings? | `template_3mf/`, as in 3dprinting/rules.md; the `B11_REF_3MF` file for B11 |
| Quit Bambu Studio before bed? | Must be quit (§ 1); the person does it |
