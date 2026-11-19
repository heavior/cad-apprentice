---
name: cad-apprentice
description: Design parts in Autodesk Fusion (Fusion 360) with the person, from a Python build script, with cad-apprentice's workflow, rules and library. Use for any CAD, Fusion 360, 3D model or 3D-print design task. Its sibling skills cover setup, the parameter test, print prep, gallery pictures and fixing a failed run.
---

# cad-apprentice: CAD in Autodesk Fusion

Every CAD and Fusion 360 task uses cad-apprentice: its design workflow, its rules and its library.
You design parts with the person from a Python build script. Fusion and the kit run on the person's
Mac, so you need a shell and Python there.

## Find the kit

The kit is the folder this skill came in: `${CLAUDE_PLUGIN_ROOT}`. If that shows as a name, not a
folder, the kit is two folders up from this file (`skills/cad-apprentice/SKILL.md`). If the person's
guidelines name their own copy of the kit, use that copy instead. The docs write the kit's folder as
`<kit>`; put the real folder in its place.

A folder is the kit only if it has `fusion/tools/fusion_outputs.py`. Some installers copy the
skills alone, without the kit (for example `npx skills add`). If the folder above isn't the kit:

1. Read `~/Library/Application Support/cad-apprentice/kit.txt`. If it names a folder that is the
   kit, use it. Setup writes it.
2. If not, tell the person the skills came without the kit, the folder with the rules, library and
   tools they need. Ask to download it from https://github.com/heavior/cad-apprentice and where to
   put it (`~/cad-apprentice` if they don't mind). Only with their OK:
   `git clone https://github.com/heavior/cad-apprentice <folder>`. Then use the setup skill.

- **Once per session,** check that Fusion uses this kit:
  `python3 <kit>/fusion/tools/fusion_outputs.py setup --check`. It changes nothing. If it says
  Fusion isn't set up for this kit (the first time, or after the plugin was updated and moved),
  use the setup skill.
- **Never update the kit yourself.** The kit changes only when the person updates it the way they
  installed it. If they ask how, point them to [How to start](../../README.md#how-to-start).

## Read before any CAD work

In the kit folder, read in this order:

1. `README.md`: what the kit does and how a design goes.
2. `fusion/lib/README.md`, before you write or change any script: how a build script is built, every
   step type, how a run works and how to read a failed one.
3. `fusion/rules.md`: the rules for every CAD job. Follow them. They cover working with the person,
   sketches, parameters, the timeline, build scripts and running them.
4. Once a design is approved for printing, use the print skill.

Give a project folder as a full path. Keep the person's design projects outside the kit folder.

The `demos/` are full design projects made with the kit. You don't need to read them to work.

## The other skills

- **setup:** set up the kit for Fusion, or check that it still works. Use it before the first design.
- **test:** run the parameter test and fix what fails.
- **print:** get an approved design ready to 3D print.
- **fix:** find and fix why a run failed or never started.
- **pictures:** take gallery pictures and close-ups of a finished design.

## Start and run a design

- **Start a new design with `new`:**
  `python3 <kit>/fusion/tools/fusion_outputs.py new NAME PROJECT_DIR --doc "Design name"`.
  It writes the entry file, its manifest and a starter `build.py` (a rounded block with every mode)
  into `PROJECT_DIR/scripts/fusion/NAME/`, and copies the entry file into Fusion's Scripts folder.
  Then replace the block with the real design.
- **Run designs with the runner,** in a background shell:
  `python3 <kit>/fusion/tools/fusion_outputs.py run NAME --mode saved`. It checks the
  script first and stops on a problem. `collect` copies the pictures and STLs into the project.
  Every tool and its options: `fusion/tools/README.md`.

## How a design goes

Follow the workflow in the kit's README.md and fusion/rules.md:

1. Show your understanding first: a picture of the idea and your questions, before any CAD.
2. After the person confirms, start the design with `fusion_outputs.py new` and build it.
3. Iterate with pictures. Each iteration is a saved version. Keep the person's own edits.
4. When the person asks for the parameter test, use the test skill.

## Evolving the library

The library grows with each design. When a design needs something the library lacks, it belongs in
the library, not in the design script.

- **An installed plugin is read-only.** An update replaces its folder, so a change there would be
  lost. Write the new step or helper in the design's own script for now, tell the person, and offer
  to send it to the kit as `CONTRIBUTING.md` says. Change the library itself only in a copy of the
  kit the person works on, named in their guidelines.

- **What goes in:** a new step type, a helper or a check that other designs can use as is, with no
  project-specific details. Everything project-specific (shapes, sizes, names) stays in the design's
  own script.
- **A new step type:** follow Adding a step type in `fusion/lib/README.md`. In short: put every value
  it sets in `spec`, raise on any refusal, add it to precheck's
  `STEPS`, add a test and run it through the runner, and list it in both READMEs.
- **A change to existing library code:** run the library tests through the runner before you call it
  done (`fusion/tests/README.md`). Never test library changes on a person's saved design.
- **A run that cost time in a new way:** add the fix to Faster iterations in `fusion/lib/README.md`.

To send a library change to the kit, follow `CONTRIBUTING.md`.
