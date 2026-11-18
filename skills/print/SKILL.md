---
name: print
description: Get a finished cad-apprentice design in Autodesk Fusion (Fusion 360) ready to 3D print. Picks the printable parts, exports STLs, gives each part a filament, and builds or updates the Bambu Studio .3mf project. Use when the person approves a design for printing, or asks for STLs, a 3MF project or test prints. To change the design, use the cad-apprentice skill.
---

# Get a design ready to print

Find the kit as the cad-apprentice skill's [Find the kit](../cad-apprentice/SKILL.md#find-the-kit)
says. If it isn't set up yet, use the setup skill first.

Read `3dprinting/rules.md` in the kit folder and follow it. In short:

- **The person sees the design first.** Show pictures of the finished design and wait for their OK
  before any STL, `.3mf` or test-print offer. Both `.3mf` scripts refuse to run without
  `--approved "<their words>"`.
- **One STL per printable part,** each with a filament chosen by its job or its color. Write the
  choice down in the project README.
- **After the first build, update the `.3mf`, never rebuild it.** The person's own settings in Bambu
  Studio must survive a new design iteration.
- **Do it all from the shell.** Open the `.3mf` in Bambu Studio once at the end, so the person can
  look. They send it to the printer themselves.

The 3MF tools are listed in `fusion/tools/README.md` § 3MF tools.
