---
name: cad-apprentice
description: Design parts in Autodesk Fusion (Fusion 360) with the person, from a Python build script, with cad-apprentice's workflow, rules and library. Use for any CAD, Fusion 360, 3D model or 3D-print design task. Its sibling skills cover setup, the parameter test, print prep, gallery pictures and fixing a failed run.
---

# cad-apprentice: CAD in Autodesk Fusion

Every CAD and Fusion 360 task uses cad-apprentice: its design workflow, its rules and its library.
You design parts with the person from a Python build script. Fusion and the kit run on the person's
Mac, so you need a shell and Python there.

## Find the kit

The kit is a folder on the person's computer: `~/cad-apprentice`, unless their guidelines name another
folder. Work from that folder, never from this plugin's install folder: the plugin folder changes
with every update, and Fusion's runner add-in and each design's entry file point at the kit folder.

- **No kit folder yet:** get the kit as [How to start](../../README.md#how-to-start) in its README says.
- **Once per session:** check whether a newer kit is out. If there is one, tell the person and offer
  to update. Update only on their yes.

## Read before any CAD work

In the kit folder, read in this order:

1. `README.md`: what the kit does and how a design goes.
2. `fusion/lib/README.md`, before you write or change any script: how a build script is built, every
   step type, how a run works and how to read a failed one.
3. `fusion/rules.md`: the rules for every CAD job. Follow them. They cover working with the person,
   sketches, parameters, the timeline, build scripts and running them.
4. Once a design is approved for printing, use the print skill.

The docs write commands for a kit in `~/cad-apprentice/...`. If the kit is in another folder, use
that folder instead. Give a project folder as a full path. Keep the person's
design projects outside the kit folder.

The `demos/` are full design projects made with the kit. You don't need to read them to work.

## The other skills

- **setup:** set up the kit for Fusion, or check that it still works. Use it before the first design.
- **test:** run the parameter test and fix what fails.
- **print:** get an approved design ready to 3D print.
- **fix:** find and fix why a run failed or never started.

## Start and run a design

- **Start a new design with `new`:**
  `python3 ~/cad-apprentice/fusion/tools/fusion_outputs.py new NAME PROJECT_DIR --doc "Design name"`.
  It writes the entry file, its manifest and a starter `build.py` (a rounded block with every mode)
  into `PROJECT_DIR/scripts/fusion/NAME/`, and copies the entry file into Fusion's Scripts folder.
  Then replace the block with the real design.
- **Run designs with the runner,** in a background shell:
  `python3 ~/cad-apprentice/fusion/tools/fusion_outputs.py run NAME --mode saved`. It checks the
  script first and stops on a problem. `collect` copies the pictures and STLs into the project.
  Every tool and its options: `fusion/tools/README.md`.

## How a design goes

Follow the workflow in the kit's README.md and fusion/rules.md:

1. Show your understanding first: a picture of the idea and your questions, before any CAD.
2. After the person confirms, start the design with `fusion_outputs.py new` and build it.
3. Iterate with pictures. Each iteration is a saved version. Keep the person's own edits.
4. When the person asks for the parameter test, use the test skill.

## Evolving the library

The library grows with each design. When a design needs something the library lacks, add it to the
library, not to the design script.

- **What goes in:** a new step type, a helper or a check that other designs can use as is, with no
  project-specific details. Everything project-specific (shapes, sizes, names) stays in the design's
  own script.
- **A new step type:** follow Adding a step type in `fusion/lib/README.md`. In short: put every value
  it sets in `spec`, wrap slow Fusion calls in `slow()`, raise on any refusal, add it to precheck's
  `STEPS`, add a test and run it through the runner, and list it in both READMEs.
- **A change to existing library code:** run the library tests through the runner before you call it
  done (`fusion/tests/README.md`). Never test library changes on a person's saved design.
- **A run that cost time in a new way:** add the fix to Faster iterations in `fusion/lib/README.md`.

To send a library change back to the kit, follow `CONTRIBUTING.md`.
