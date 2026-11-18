# cad_apprentice: library tests

For agents changing the library. To test your own design, see [Testing your design](../../README.md#testing-your-design).

All tests run in throwaway designs and never touch a saved design, except scenarios K and N, which
use their own test folder. Run each through the runner add-in by writing a request to
`tests/run/requests/<id>.json` (write it as `.tmp`, then rename it). The `file` in a request is
relative to the kit's `fusion/` folder, or a full path. The result lands in `tests/run/results/<id>.json` with the time it took. A test that returns
`{'status': 'pass' or 'fail', ...}` sets the result's `status` to that; any other return gives `done`, which
only means the test finished, not that it passed.

| Test | What it checks | Request | Last run |
| --- | --- | --- | --- |
| [test_features.py](test_features.py) | every feature type: build, change each one's own values (each must edit in place or say why it replaced), then a no-change run. Every feature ends healthy | `{"id": "features", "file": "tests/test_features.py", "args": {}}` | pass (2026-11-17, every Fusion call timed): 137 created, 31 updated, 13 replaced, 230 same over 3 runs, 10–12 s; 43,026 Fusion calls, 10.3–11.2 s with the timers off |
| [test_edit_in_place.py](test_edit_in_place.py) | a two-set fillet and a loft edited in place after a redraw, with a hand-made block after them. "Same feature" is checked by token string and by `findEntityByToken`, and any disagreement is listed in `token_disagree` | same, with its file | pass (2026-11-17), 1.2 s; the two checks agreed 8 of 8 |
| [test_joints.py](test_joints.py) | three joints and an as-built joint: values, sides and motion edited in place, a hand-made joint after them kept | same, with its file | pass (2026-11-17): 19 created, 4 updated, 0 replaced, 34 same, 2.9 s |
| [upsert_suite.py](upsert_suite.py) | the 99 scenarios in [upsert-test-scenarios.md](upsert-test-scenarios.md): parameters, edits, redraws, order, groups, parts, hand edits, saving and going back, a Part-intent design | `{"id": "...", "file": "tests/upsert_suite.py", "args": {}}`, or `"args": {"ids": ["E3"]}` for some | 99 of 99 pass (2026-11-17, every Fusion call timed), 638 s; one cloud save took 60 s |
| [test_components.py](test_components.py) | parts and nested parts. Also runs with ▶ from [FusionUpsertTest.py](FusionUpsertTest.py) | same, with its file | pass (2026-11-17), 28 of 28 checks |
| [test_precheck.py](../lib/cad_apprentice/test_precheck.py) | the read-ahead check, without Fusion: `python3 ~/cad-apprentice/fusion/lib/cad_apprentice/test_precheck.py` | — | 19 cases pass (2026-11-16) |
| [test_ranges.py](../lib/cad_apprentice/test_ranges.py) | parameter ranges, without Fusion: `python3 ~/cad-apprentice/fusion/lib/cad_apprentice/test_ranges.py` | — | 15 cases pass |
| [test_thin.py](../lib/cad_apprentice/test_thin.py) | the thin-part log, without Fusion: `python3 ~/cad-apprentice/fusion/lib/cad_apprentice/test_thin.py` | — | 9 cases pass |
| [check_plan_ids.py](check_plan_ids.py) | that every plan id in [upsert-test-scenarios.md](upsert-test-scenarios.md) is run by a scenario, or says "covered by", "planned" or "dropped", and that every scenario is in the plan. Without Fusion: `python3 check_plan_ids.py`; exits 1 on a gap | — | no gaps |
| [stl_check.py](stl_check.py) | exported STLs, without Fusion: watertight, faces turned the same way, one piece, and the size. `python3 stl_check.py <file.stl>` | — | — |
| [ping.py](ping.py) | that the runner answers; it changes nothing | `{"id": "...", "file": "tests/ping.py", "args": {}}` | — |

Before a run, check the runner is free: `tests/run/active/` and `tests/run/requests/` should be empty.
