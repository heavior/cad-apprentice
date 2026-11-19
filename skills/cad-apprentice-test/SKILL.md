---
name: cad-apprentice-test
description: Run the parameter test on a cad-apprentice design in Autodesk Fusion (Fusion 360) and fix what fails. It sets each parameter across its range, checks the design still builds, then checks it comes back the same. Use when the person asks to test a design, make it robust, or test some of its parameters. For a run that fails outside the test, use the cad-apprentice-fix skill.
---

# Test a design

Find the kit as the cad-apprentice skill's [Find the kit](../cad-apprentice/SKILL.md#find-the-kit)
says. If it isn't set up yet, use the cad-apprentice-setup skill first.

## Read first

In the kit folder:

1. `README.md` § Testing your design: what the test does and how the person asks for it.
2. `fusion/lib/README.md` § The parameter test: ranges, the stages, and the modes that pick them.
3. `fusion/rules.md`, before you change the design. Follow it.

## Run it

- Run it in a background shell. A full test can take a while:
  `python3 <kit>/fusion/tools/fusion_outputs.py run NAME --mode check`.
- For some parameters only: `--mode check:width,height`.
- Random sets only after the first three stages pass, and only when the person asks:
  `--mode check:random=50`.

## When it fails

Look up the log's last lines in `fusion/lib/README.md` § When a run fails.

- A value a person would reasonably pick must work: fix the design for it.
- For an edge case no one will use, narrow the range instead of making the design more complex.
- Never narrow a range the person set without asking.
- Run the test again after each fix. Show the person what you chose with the next iteration.
