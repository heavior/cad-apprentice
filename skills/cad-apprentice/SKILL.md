---
name: cad-apprentice
description: Design parts in Autodesk Fusion (Fusion 360) with the person, from a Python build script, with cad-apprentice's workflow, rules and library. Use for any CAD, Fusion 360, 3D model or 3D-print design task, including setting up the kit and running its parameter test.
---

# cad-apprentice: CAD in Autodesk Fusion

Every CAD and Fusion 360 task uses cad-apprentice: its design workflow, its rules and its library.
Fusion and the kit run on the person's Mac, so you need a shell and Python there.

## Find the kit

The kit is a folder on the person's computer: `~/cad-apprentice`, unless their guidelines name another
folder. Work from that folder, never from this plugin's install folder: the plugin folder changes
with every update, and Fusion's runner add-in and each design's entry file point at the kit folder.

- **No kit folder yet:** `git clone https://github.com/heavior/cad-apprentice ~/cad-apprentice`.
- **Kit folder there:** `git -C ~/cad-apprentice pull --ff-only` once per session, to get fixes.

## Read before any CAD work

In the kit folder, read in this order:

1. `CLAUDE.md`: what to read and how to start and run a design.
2. `README.md`: what the kit does and how a design goes.
3. `fusion/lib/README.md`: how a build script is built, every step type, how to read a failed run.
4. `fusion/rules.md`: the rules for every CAD job. Follow them.
5. `3dprinting/rules.md`, once a design is approved for printing.

The docs write commands from the repo the kit came from, as `projects/hobby/cad-apprentice/...`. Run
them with the kit folder instead, for example
`python3 ~/cad-apprentice/fusion/tools/fusion_outputs.py run NAME --mode saved`. Give a project folder
as a full path. Keep the person's design projects outside the kit folder.

## Set up, once

Follow the kit's SETUP.md. Link the runner add-in into Fusion's AddIns folder (a link,
not a copy):
`ln -s ~/cad-apprentice/fusion/runner/entry ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns/UpsertTestRunner`.
Ask the person to restart Fusion. Then check the runner with `tests/ping.py`; the request is in
`fusion/tests/README.md`. Tell the person what you set up and whether the check passed.

## How a design goes

Follow the workflow in the kit's README.md and fusion/rules.md:

1. Show your understanding first: a picture of the idea and your questions, before any CAD.
2. After the person confirms, start the design with `fusion_outputs.py new` and build it.
3. Iterate with pictures. Each iteration is a saved version. Keep the person's own edits.
4. When the person asks for the parameter test, follow Testing your design in the README.
