# Contributing to cad-apprentice

Thanks for helping. Bug reports, fixes, new step types and doc fixes are all welcome.

## Report a problem

Open an issue at [github.com/heavior/cad-apprentice/issues](https://github.com/heavior/cad-apprentice/issues).
Say what you asked for, what happened, and paste the last lines of the run's log. Leave out anything
private about your design.

## Send a change

1. Fork the repository, clone it and make your change on a branch. Run
   `python3 fusion/tools/fusion_outputs.py setup` from your clone and restart Fusion, so Fusion runs
   your copy of the kit.
2. Keep the change general. Shapes, sizes and names from your own design stay in your design's
   script; only steps, helpers and checks that other designs can use go into the library.
3. Run the tests that cover what you changed (below).
4. Open a pull request. Say what the change does and which design needed it.

## Run the tests

- **Without Fusion,** from the kit folder:
  `python3 fusion/lib/cad_apprentice/test_precheck.py`,
  `python3 fusion/lib/cad_apprentice/test_ranges.py` and
  `python3 fusion/lib/cad_apprentice/test_thin.py`.
- **Library changes,** in Fusion through the runner add-in: the tests in
  [fusion/tests/README.md](fusion/tests/README.md). They run in throwaway designs.
- **3MF tools:** `python3 3dprinting/tests/run_tests.py`, as
  [3dprinting/3mf-test-scenarios.md](3dprinting/3mf-test-scenarios.md) says.

## If an AI agent makes the change

Point it at the skill, [skills/cad-apprentice/SKILL.md](skills/cad-apprentice/SKILL.md), and its
[Evolving the library](skills/cad-apprentice/SKILL.md#evolving-the-library) section. A new step type
follows Adding a step type in [fusion/lib/README.md](fusion/lib/README.md). This prompt works:

```
Read CONTRIBUTING.md and the cad-apprentice skill. Make the change, run the tests that cover it,
and open a pull request that says what the change does and which design needed it.
```

## License

By contributing, you agree that your work is shared under the [MIT License](LICENSE).
