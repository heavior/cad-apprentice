---
name: setup
description: Set up cad-apprentice for Autodesk Fusion (Fusion 360) on the person's Mac, or check that it still works. Points Fusion at the kit, adds the runner add-in to Fusion and checks that the runner answers. Use when the person asks to set up or check cad-apprentice, or when another cad-apprentice skill finds Fusion isn't set up for the kit. To design a part, use the cad-apprentice skill.
---

# Set up cad-apprentice

Fusion and the kit run on the person's Mac, so you need a shell and Python there.

1. **Find the kit,** as the cad-apprentice skill's [Find the kit](../cad-apprentice/SKILL.md#find-the-kit)
   says.
2. **Read the kit's `SETUP.md`.** It says what setup writes and where.
3. **Tell the person what setup does, and ask first.** It writes the kit's folder to
   `~/Library/Application Support/cad-apprentice/kit.txt` and copies the runner add-in into Fusion's
   AddIns folder as `CadApprenticeRunner`. The add-in starts with Fusion and runs the Python files
   that requests in `~/Library/Application Support/cad-apprentice/run/requests/` name. Go on only on
   their yes.
4. **Run setup:** `python3 <kit>/fusion/tools/fusion_outputs.py setup`. If it says an older add-in
   is in the AddIns folder, tell the person.
5. **Ask the person to restart Fusion,** so the add-in loads the kit.
6. **Check the runner with `tests/ping.py`.** The request and where its result lands are in
   `fusion/tests/README.md`. It changes nothing.
7. **Tell the person** what you set up and whether the check passed. Then offer to start a design
   with the cad-apprentice skill.
