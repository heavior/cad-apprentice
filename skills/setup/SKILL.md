---
name: setup
description: Set up cad-apprentice for Autodesk Fusion (Fusion 360) on the person's Mac, or check that it still works. Gets the kit, links the runner add-in into Fusion and checks that the runner answers. Use when the person asks to install, set up or check cad-apprentice, or when another cad-apprentice skill finds the kit or the runner missing. To design a part, use the cad-apprentice skill.
---

# Set up cad-apprentice

Fusion and the kit run on the person's Mac, so you need a shell and Python there.

1. **Find the kit,** as the cad-apprentice skill's [Find the kit](../cad-apprentice/SKILL.md#find-the-kit)
   says: `~/cad-apprentice`, unless the person's guidelines name another folder. If it isn't there,
   get it as [How to start](../../README.md#how-to-start) in the kit's README says.
2. **Read the kit's `SETUP.md`.** Run its commands from the kit folder, not from the repo path they
   show.
3. **Link the runner add-in** into Fusion's AddIns folder (a link, not a copy):
   `ln -s ~/cad-apprentice/fusion/runner/entry ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns/UpsertTestRunner`.
   If the link is already there and points at the kit, leave it.
4. **Ask the person to restart Fusion,** so the add-in starts.
5. **Check the runner with `tests/ping.py`.** The request and where its result lands are in
   `fusion/tests/README.md`. It changes nothing.
6. **Tell the person** what you set up and whether the check passed. Then offer to start a design
   with the cad-apprentice skill.
