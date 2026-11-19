---
name: cad-apprentice-fix
description: Find and fix why a cad-apprentice run in Autodesk Fusion (Fusion 360) failed or never started. Reads the run's log from the bottom, matches its last lines, and fixes the build script or the library. Use when a run ends in BROKEN, STOPPED, a traceback or WARNINGS, or when the runner doesn't answer. A failed parameter test goes to the cad-apprentice-test skill.
---

# Fix a failed run

Find the kit as the cad-apprentice skill's [Find the kit](../cad-apprentice/SKILL.md#find-the-kit)
says.

1. **Read the log from the bottom.** Look up its last lines in `fusion/lib/README.md` § When a run
   fails. On `BROKEN` and `STOPPED` the design has already gone back to its last saved version.
2. **Read `fusion/rules.md` before you change the script,** and follow it. Many fixes are in its
   Features that survive parameter changes and Fusion facts that cost time.
3. **A run that never started:** check the runner with `tests/ping.py`, as `fusion/tests/README.md`
   says. If it doesn't answer, follow Running a script in `fusion/rules.md`. If the add-in isn't
   there at all, use the cad-apprentice-setup skill.
4. **Fix the design's own script,** unless the library is at fault. Then follow the cad-apprentice
   skill's [Evolving the library](../cad-apprentice/SKILL.md#evolving-the-library), and run the
   library tests.
5. **Run it again in the same mode** and read the log and the pictures.
6. **Tell the person** in a line what broke and what you changed.

A failure that cost time in a new way goes into `fusion/lib/README.md` § Faster iterations.
