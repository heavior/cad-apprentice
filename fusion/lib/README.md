# cad_apprentice: script reference

For agents writing a design script. People don't need this file; the [README](../../README.md) has
what the kit does.

## Writing a script

A design script defines `run(context)`. It opens or makes the design, then describes it:

```python
def run(context):
    out = cad_apprentice.LiveLog(LOG)          # a log file that is written as it grows
    b = None
    try:
        doc = ...                             # the saved design ('saved' mode) or a new tab
        des = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
        b = cad_apprentice.Builder(des, doc, out)
        describe(b)                           # every b.param / b.sketch / b.extrude ... call
        if b.finish():                        # checks every feature; goes back if one is broken
            b.save('What changed in this version')
            out.append('DONE')
    except:
        out.append(traceback.format_exc())
        if b:
            b.abort('see the error above')    # logs STOPPED and goes back to the last save
    out.close()
```

The starter design in [template/build.py](../template/build.py) is a complete small example with
all the modes; `fusion_outputs.py new` copies it into a new project. The rules for working in Fusion are in
[fusion/rules.md](../rules.md).

The rules every step follows:

- **The key** (first argument) never changes. A hidden attribute on the feature holds it, so
  renaming a feature in Fusion is fine. The second argument is the name shown in the timeline.
- **Geometry is passed as a function**, for example `lambda: comp.xYConstructionPlane` or
  `lambda: [(edges(), '2 mm')]`. The library calls it when it builds or edits the step.
- **`uses=[...]`** names the steps a step takes geometry from. When one of them is rerun, this one
  picks its geometry again. A name in `uses` that no earlier step has stops the run before anything
  is built.
- **What the fingerprint can't see.** A change to one of these doesn't rerun the step; copy the
  value into a plain variable or a `spec=` first, as `d = v['cham']`, then `lambda: [(edges(), d)]`:
  - values read from a dict or list;
  - a tuple with anything but plain values in it;
  - code in other files (helpers.py counts as the script's own);
  - a `functools.partial`, and the keyword defaults of a function passed in.

  precheck notes a step function that reads a dict by a fixed key (`lambda: g['cham']`), the most
  common of these.

  A Fusion object in a step's spec stops the run: it prints differently each run, so the step would
  rebuild every time. Pass a function that finds it, or its name. A set is fine; it is sorted first.
- **Expressions** like `'wall * 4'` or `'2 mm'` work wherever a size or angle goes. Parameter values
  are not part of the fingerprint, since Fusion recalculates those itself.

## Supported steps

"Edits in place" means a change to that value edits the existing feature. Anything else replaces
the step, and the log says which value it was when Fusion can't edit it in place (`replaced Trim:
operation changed, which can't be edited in place`). A replaced step is deleted and made again at its spot, and that is refused when a hand-made feature
comes after it. Every step also takes `spec=()` (extra values that should count as a change) and
`uses=()`, except: `param`, `group`, `component` and `take_over` take neither, and `base_body` takes
`spec=` but not `uses=`.

| Method | Makes | Edits in place | Tested in |
| --- | --- | --- | --- |
| `param(name, expr, unit, comment, favorite=False, was=None, range=None, step=None)` | a user parameter; `favorite` stars it for MakerWorld's Customize; `was` gives its old name (or names), so a rename keeps the parameter; `range=(low, high)` and `step` give the values it may take ([Ranges](#ranges)) | value, comment, star, range. A value changed by hand is kept | scenarios B |
| `component(key, name)` (a `with` block) | a part; blocks can nest | — | `test_components.py`, scenarios I |
| `group(name)` (a `with` block) | a timeline group | — | scenarios H |
| `sketch(key, name, plane, draw)` | a sketch drawn by `draw(sketch)` | never: redrawn whole, and the steps that use it are repointed | scenarios D, every test |
| `plane(key, name, make)` | any construction plane `make` returns | — | `test_components.py`, scenarios |
| `offset_plane(key, name, base, offset, along=None)` | a plane at a distance | offset | `test_features.py` |
| `angled_plane(key, name, line, angle, plane)` | a plane at an angle | angle | `test_features.py` |
| `mid_plane(key, name, a, b)` | a plane halfway between two | sides (built in the test, a change not tested) | `test_features.py` |
| `axis(key, name, how, a, b=None)` | an axis: `'two_planes'`, `'line'`, `'two_points'`, `'normal'` | inputs (built in the test, a change not tested) | `test_features.py` |
| `point(key, name, how, a, b=None)` | a point: `'point'`, `'two_lines'`, `'center'` | inputs (built in the test, a change not tested) | `test_features.py` |
| `extrude(key, name, sketch, op, distance=, symmetric=, taper=, thin=, profile=, participants=, body_name=)` | an extrude | distance, symmetric distance, taper, operation, profile, participants, body name, thin wall thickness and side. Dropping `participants` replaces it | `test_features.py`, scenarios C |
| `revolve(key, name, sketch, axis, op, angle='360 deg', symmetric=False, participants=None, body_name=None, profile=None)` | a revolve | angle, axis, operation, profile, participants, body name. Dropping `participants` replaces it | `test_features.py` |
| `sweep(key, name, sketch, path, op, participants=None, body_name=None, profile=None, chain=True)` | a sweep | path, profile, operation, participants, body name. Dropping `participants` replaces it | `test_features.py` |
| `pipe(key, name, path, size, op, hollow=None)` | a pipe | size, path, wall, participants, body name. A new operation, a wall added or taken away, or dropping `participants` replaces it | `test_features.py` |
| `loft(key, name, sections, op)` | a loft | sections, also redrawn or moved to another sketch. A different number of sections, or dropping `participants`, replaces it | `test_features.py`, `test_edit_in_place.py` |
| `hole(key, name, points, diameter, depth=None, kind='simple', head=None)` | simple, counterbore or countersink holes | diameter, depth, head. A new kind, or a depth changed to or from through all, replaces it | `test_features.py` (all three kinds) |
| `combine(key, name, target, tools, op, body_name=None)` | join, cut or intersect | target, tools, body name. A new operation replaces it | `test_features.py`, scenarios C |
| `fillet(key, name, sets)` | a fillet; each set is `(edges, r)`, `(edges, 'chord', length)` or `(edges, 'variable', start, end, mids)` | radius, chord, variable radii and mid points, edges, two sets at once | `test_features.py`, `test_edit_in_place.py` (G4) |
| `chamfer(key, name, sets)` | a chamfer; each set is `(edges, d)`, `(edges, 'two', d1, d2)` or `(edges, 'angle', d, angle)` | distances, angle, edges. A set that changes kind is replaced | `test_features.py` |
| `base_body(key, name, make_body)` | a base feature holding a body you make with the API | replaced | scenarios (model) |
| `move(key, name, bodies, x, y, z)` | a move | distances, bodies | scenarios |
| `turn(key, name, bodies, axis, angle)` | a move that rotates about an axis | angle | `test_features.py` |
| `copy(key, name, body)` | a copy of a body | replaced | `test_features.py` |
| `rect_pattern(key, name, bodies, axis1, n1, d1, axis2, n2, d2, adjust=False, compute=None)` | a rectangular pattern | counts, spacing, bodies, both directions (an edge counts by which edge it is). `compute` is `'identical'`, `'optimized'` or `'adjust'` ([rules.md rule 32](../rules.md)); a new one replaces the step. Left out (or `adjust=True`), nothing changes on designs built before it: Fusion's API default is Adjust, the slowest | `test_features.py`, scenarios |
| `circular_pattern(key, name, items, axis, n, angle='360 deg', symmetric=False, adjust=False, compute=None)` | a circular pattern | count, angle, items, symmetric. With `symmetric=True` the angle covers both sides together, so double a one-side angle. A new axis or a new `compute` (see `rect_pattern`) replaces it | `test_features.py` |
| `path_pattern(key, name, items, path, n, spacing, compute=None)` | a pattern along a path | count, spacing. New items, a new path, a new `chain` or a new `compute` (see `rect_pattern`) replaces it | `test_features.py` |
| `mirror(key, name, items, plane, combine=False, compute=None)` | a mirror | plane, items, body name. Turning `combine` on or off, or a new `compute` (see `rect_pattern`), replaces it | `test_features.py` |
| `split_body(key, name, body, tool, extend=True)` | a split; `extend` grows the tool to cut all the way through | tool. A new body replaces it | `test_features.py` |
| `shell(key, name, faces, thickness)` | a shell | thickness, faces (a second open face added) | `test_features.py` |
| `scale(key, name, bodies, point, factor)` | a scale | factor. New bodies or a new point replaces it | `test_features.py` |
| `remove(key, name, body)` | a remove | replaced | `test_features.py` |
| `joint(key, name, one, two, motion='rigid', axis='z', offset=None, angle=None, flip=False)` | a joint between two parts; `motion` = `'rigid'`, `'revolute'` or `'slider'` | sides, motion, axis, offset, angle, flip | `test_joints.py` |
| `as_built_joint(key, name, one, two, motion='rigid', axis='z', at=None)` | an as-built joint between two occurrences; `at` is needed unless rigid | motion, axis, `at`. Other parts replace it | `test_joints.py` |
| `step(key, name, make, update=None, ...)` | anything else: `make()` builds it, `update(feature)` edits it | whatever `update` sets | every test |
| `take_over(key, name, entity)` | tags a feature that is already there, so the script owns it from now on | — | scenario J6 |

More on some of these:

- **Joints.** `one` and `two` return a vertex, sketch point, construction point, joint origin or a
  ready `JointGeometry`, in any part. A point inside a part is seen from the top through that part's
  one occurrence (a part placed twice raises). Fusion only edits a joint with the timeline marker
  before it, and a joint past the marker can't be read, so the library moves the marker as needed.
  An as-built joint's `at` point is set together with its motion: Fusion refuses one without the
  other. Hand-made joints have no key, so a run leaves them alone.
- **Extrude profile:** `profile=lambda s: ...` picks the profile (or an ObjectCollection of them)
  when `profiles.item(0)` is not the right one.
- **Planes:** `offset_plane`'s `along` = 0, 1 or 2 measures the offset toward +X, +Y or +Z,
  whichever way the base plane's normal points.
- **Sweep, pipe and path pattern:** `path` returns a curve or a list of curves. `chain=True` follows
  the curves joined to them; `chain=False` takes only the ones given.
- **Thin extrude:** `thin` is a thickness, or `(thickness, 'side1' | 'center' | 'side2')`.
- **Variable fillet:** `(edges, 'variable', start, end, (('0.5', '2 mm'), ...))`, each mid point a
  position from 0 to 1 and a radius, on one edge or a chain of tangent edges in order.
- **`body(key, i=0)`** returns a step's body. It fails with a clear message when the step has no
  such body, which happens when a key from an older script is reused. Give the step a new key.
- **Shared helpers:** [helpers.py](cad_apprentice/helpers.py) holds the small functions design scripts share:
  `mm`, `p3`, `box`, sketch tools (`sketch_tools`, `report_sketch`, `to_sk`, `projected`, `axis`,
  `rectangle_n`, `along`, `keep_along`, `level_along`, `every_profile`, `flat_in`, and `H` and `V` for
  a dimension's direction), refusals that go in the log instead of stopping (`trying` runs one
  constraint, `sizer` one dimension set to an expression), faces and bodies
  (`flat_face`, `face_edges`, `main_body`, `loose_pieces`), pictures (`camera`, `planes_off`,
  `hide_sketches`, `sketch_pictures`: each sketch alone, square on), the log's closing `report` (sketches,
  timeline health, bodies, favorites), STL files (`write_stl`) and the saved design (`saved_design`, `wipe`,
  `order_favorites`). Import what
  you need: `from cad_apprentice.helpers import mm, p3, sketch_tools`.
- **`tag(entity, name)` and `tagged(sketch, name)`** mark a sketch point or curve so another sketch
  can find and project it after a redraw.

## How a run works

- **Reading the design:** every run starts with the timeline marker at the end, so every step the
  library made can be read.
- **What counts as a change:** each feature stores a fingerprint of the script's inputs, including
  the code of any drawing or edge-picking function, and the `uses` list. A step whose fingerprint
  is the same is skipped. An edge, face or sketch line passed as it is counts by its body or sketch
  and where it sits, not only by its kind, so a pattern moved to another edge is noticed.
- **Values that can't be edited in place:** a step passes them to `step()` as `fixed=(('operation',
  operation), ...)`. Each feature stores them, and a change to one replaces the feature instead of
  editing it. A feature made before this record was kept is edited in place one more time, then
  records them: replacing it could fail on hand-made features after it.
- **Edit or replace:** a changed step is edited in place when the method knows how (the table
  above). Otherwise it is replaced. A replace is refused, with an error, if any feature after it
  isn't the library's (`_refuse_if_not_last`). Editing in place and changing parameters go ahead.
- **Sketches** are redrawn whole: a new sketch goes right after the old one, the features that use
  it are repointed, then the old one is deleted. Clearing the same sketch doesn't work: Fusion
  raises an error when an extrude is repointed after the curves of its profile were deleted. A sketch the script puts on another plane is redrawn there.
- **Order:** a step the script now puts after a step that sits later in the timeline is moved to
  its new spot. If Fusion won't move it, it's rebuilt there.
- **Parts:** inside `with b.component(...)`, steps go in that part. Without one, they go in the top
  component and the log says so. A step the script moves to another part is refused: move it by hand
  first. A Part-intent design has no subcomponents, so everything stays in the top component.
- **Groups:** a step inside a collapsed group can't be rolled to, so a run opens every group, works,
  then closes the ones it opened. Steps in a `component()` block outside any group go in a group named
  after the part. A `group('legs')` inside it is named `Frame · legs`, since Fusion has no group
  inside a group. Keep a part's loose steps before or after its groups, not between them.
- **Parameters:** a value changed by hand since the last run is kept and reported. A parameter the
  library made and the script no longer lists is removed once nothing uses it. A favorite that is a
  formula stops the run: MakerWorld's Customize can't show it.
- **Removed steps:** a step dropped from the script is deleted on the next run. Features the library
  didn't make are never deleted. A step Fusion deletes along with a removed one is made again at its
  spot in the same run. So is one it deletes along with a replaced step; the log calls it replaced,
  "deleted along with" that step.
- **Taking over an older design:** tag what's already there with `take_over(key, name, ent)`, then
  run the script once. That run accepts the feature as it is and stores its fingerprint. Call it
  only when the feature matches what the script says.
- **Checking and going back:** `finish()` checks every feature. If one is broken, it closes the
  design without saving and reopens the last saved version. `abort(why)` does the same after an
  error. A feature that was already broken before the run is reported and left alone; it doesn't
  send the run back.
- **Restore points:** `save()` saves only when something changed. If the design had unsaved changes
  when the run started, the Builder saves them first, as their own version, before it touches
  anything. If that save fails, the run stops before any change. The go-back waits for a save to
  show up in the cloud. A design never saved has nothing to go back to, and the log says so.
- **After a clean run:** `wipe()` returns the version from before the wipe. Pass it to the Builder
  as `go_back_to=`, so a failed rebuild goes back to the full design, not an empty one.
- **When going back fails:** the run logs `COULD NOT GO BACK`, keeps its own error, and stores the
  last good version in the design (attribute `go_back_to`). The next run in that tab goes back there
  if it fails too, and saves no restore point of the half-built tab. A run that finishes well clears
  the mark and saves, even when it changed nothing else. Nothing waits for a person.
- **Timing:** while a `LiveLog` is open, every call into Fusion's API is timed. A call that takes a
  second or more writes "Fusion Class.method: done in 4.2 s" ("failed after" if it raised). The call
  running now is kept in the log's `.now` file, so a stuck run names its call. Only the run's own
  thread is timed, and the timers come off when the log closes. `with cad_apprentice.slow(log,
  'what'):` names a stretch of work in the log, so the timings say what the calls were for.
  `set_param(log, p, expr)` and `catch_up(log)` (for `adsk.doEvents()`) do it in one line.

## The parameter test

`b.trials()` sets parameters to test values, lets Fusion recompute, then puts them back
([fusion/rules.md](../rules.md) rule 19). Run it after a save, so a broken design can go back. The
template runs it in the `check` and `night` modes.

### Ranges

Every plain-value parameter gets a range: the values it is meant to take, low to high in steps. Guess
it, generously, when you make the parameter, and offer the person a review when the iteration is
ready ([rules](../rules.md) 19).
`b.param('width', '40 mm', 'mm', 'block width', True, range=('20 mm', '80 mm'), step='5 mm')`. A bare
number takes the parameter's unit, and a count with no unit steps by 1 if `step` is left out. The
test tries values from the range, and the same numbers are the favorites' slider limits on
MakerWorld's Customize page.

The library saves each range in the design (an attribute named `range.<name>`), so a later run, or a
`check:` run of one parameter, still knows it. A changed range counts as a change and is saved. The
range moves with a renamed parameter and is deleted with a dropped one.

### The stages

The test runs in stages, quick ones first, and stops after the first stage with a failure. A
broken end shows up in a few trials, before the slow stages run.

1. **ends:** each parameter alone at the low and the high end of its range. When an end fails, the
   test halves the gap to the parameter's value until it finds the last value that works, logs
   `RANGE TOO WIDE: name works from A to B`, and puts it in `b.trials_held[name] = (A, B)`.
2. **steps:** each parameter alone, one step either side of its value.
3. **extremes:** every ranged parameter at its low end at once (`all low`), then every one at its
   high end (`all high`), then all high again but set from all low (`all low, then all high`).
   Fusion recomputes after each value, so the way between two sets matters: a sketch can solve
   from the usual values and fail from the far end of every range.
4. **random,** only when asked: `runs` sets of values picked at random from each range, all
   parameters at once. The log has the seed, so a failed set can be run again. Offer it to the
   person once the other stages pass.

A trial already made in an earlier stage isn't made again. A failed set logs every value in it
(`  the set: ...`).

A plain value with no range falls back to a step down and a step up: one less and one more for a
whole-number count (never below 1), else 0.8 and 1.25 times it. It is left out of extremes and
random, and the log says `no range for ...`. A formula is never tried.

### Running it

- **What fails a trial:** a new error or warning, a sketch that is no longer fully constrained, a
  sketch that didn't solve, a value Fusion refuses, or a problem from `more(des)`. A sketch that
  can't solve a new value keeps its old shape and warns only on itself: its timeline step stays
  healthy, so `warnings()` asks every sketch the library made too.
- **Coming back:** after each trial the old values go back, and the design must be as before: no new
  error, and the same `size()` (volume, body count, face count). If it isn't, the test stops there and
  returns False, and the caller aborts. Failed trials are in `b.trials_failed` and the log.
- **Afterwards, `b.back_to_saved()`:** the values are back, but Fusion still counts the tab as
  changed. Left like that, closing it pops up Fusion's "Unsaved changes" dialog, and the runner
  refuses the next run. `back_to_saved()` closes the tab without saving and reopens the saved
  version. Call it last, after the test passes or is stopped: the design and tab objects are stale
  after it. The template does this.
- **Arguments:** `tests=('ends', 'steps', 'extremes')` picks the stages, in order; add `'random'`
  for random sets, with `runs=20` and `seed=` (the time if left out). `values=[(name, value), ...]`
  tries a name at these values instead of its range. `skip=[...]` names parameters not to try; give
  each one's reason in a comment. `only=[...]` tries just these. `stop=path` ends the test when that
  file shows up, since Fusion can't stop a running script. `size=` and `more=` replace the size check
  and add checks of your own.
- **The mode picks the test.** `MODE, ONLY, TEST = cad_apprentice.split_mode(MODE)` splits it, and
  `b.trials(only=ONLY, **TEST)` uses it:

| Mode | Runs |
| --- | --- |
| `check` | ends, steps, extremes |
| `check:width,height` | the same, for those parameters only |
| `check:extremes` | one stage: `ends`, `steps`, `extremes` or `random` |
| `check:random=50,seed=7` | ends, steps, extremes, then 50 random sets from seed 7 |
| `check:width,random=50` | names and tests mix |

### Thin parts

A detail sized as a share of a parent part ([rules](../rules.md) 9) can print thinner than one
nozzle line on a small model. That can be fine, so [thin.py](cad_apprentice/thin.py) only reports it.
`watch = thin.Watch(names, out)` takes the mm parameters to watch. `watch(des, label)` logs
`THIN (under 0.4 mm) label: name 0.21 mm, ...` when any is under 0.4 mm. Call it after the build
and inside `more=` for each trial, and return only the real problems from `more=` so a thin part
never fails a trial. `watch.summary()` logs how many checks had thin parts and the thinnest one.
Tests: `python3 <kit>/fusion/lib/cad_apprentice/test_thin.py`.

## When a run fails

Read the log from the bottom. Its last line says how the run ended; the lines above say what led
there. On `BROKEN` and `STOPPED` the design has gone back to its last saved version, so nothing half
done was saved.

### How the log ends

| Last lines | What happened | What to do |
| --- | --- | --- |
| `DONE` | the run worked | read the `steps:` line and the pictures |
| `BROKEN: <feature>: <Fusion's message>` | `finish()` found a feature with an error, one of the person's features that warns since this run, or one that is gone | find Fusion's message in the tables below |
| `STOPPED: <why>`, with a traceback above it | the script or the library raised partway through | the traceback's last line names the step; see the tables below |
| a traceback and no `STOPPED` | it failed before the Builder existed, for example opening the saved design | read the traceback's last line |
| `WARNINGS: ...` | features that warn but don't stop the run | fix them anyway: a warned feature looks fine until someone opens it |
| `still loose: ...` under a sketch | the sketch is not fully constrained | constrain the points listed ([rules](../rules.md) 13 and 26) |
| `RERUN CHANGED SOMETHING` | the second run of `check` changed steps, so a step's inputs differ between runs | the `steps:` line above names them; look for inputs that change each run |
| `TRIAL FAILED: name = value: ...` | the design breaks at that value | fix the design for a value a person would reasonably pick, else narrow the range to just inside what works (rules 19, 31) |
| `RANGE TOO WIDE: name works from A to B` | an end of the range fails | fix the design if a person would reasonably pick that value, else narrow the range to A to B; tell the person which ([rules](../rules.md) 19) |
| `the ends stage failed, so ... did not run` | the test stopped early, on purpose | fix the failures above, then run `check` again |
| `DID NOT COME BACK after name = value` | the trial lost a reference that stayed lost. `bodies:` names each body that moved, changed size, or was gone or renamed after the old values went back, even when the totals match | usually rule 23, 24 or 30 below |

### Messages from the library

| Message | Cause | Fix |
| --- | --- | --- |
| `step X uses Y, but no step before it has that key` | a typo in `uses`, or Y comes later in `describe()` | fix the name or the order |
| `step X is used twice` | two steps have the same key | give one a new key |
| `favorite X = ... is a formula` | MakerWorld's Customize shows only plain values | give the numbers their own parameter and make the favorite plain |
| `Fusion refused parameter X ... the name may be taken by a function` | the name clashes with one of Fusion's functions, like `floor` | rename the parameter |
| `parameter X can't change its unit` | something uses it, and the API can't change a unit | use a new name |
| `parameter X can't be renamed to Y: the design already has both` | both names exist | ask the person which to delete by hand |
| `X is in component A, but the script now puts it in B` | the library doesn't move steps between parts | move it by hand first, or run `clean` |
| `X can only be replaced by deleting it, which could take this with it: ...` | features the library didn't make sit after it | ask the person, or run `clean` |
| `step X has no body N now, a later step took it` | the key meant something else in an older script | give the step a new key |
| `X cuts A, not only B` | Fusion didn't keep the extrude's `participants` when it was edited | check that `participants` returns the right bodies, then run `clean` |
| `no flat face facing ... at ... mm on ...` | `flat_face` found no face at that height | check the height: the API works in cm, and the log lists the faces it saw |
| `no saved NAME in PROJECT` | the design was never saved, or another project is open | build it once with `--mode new`, or open the right project |
| `the parameter test names X, but the design has no such parameter` | a typo in `values`, `skip`, `only` or `check:<names>` | fix the name |
| `parameter X = ... has a range, but only a plain value can have one` | a range on a formula | drop the range; the formula follows the parameters it uses |
| `parameter X has a range but no step` | a size with `range=` and no `step=` | give the size a slider moves by |
| `parameter X: range value ... is not a plain number in mm` | a range in another unit, or a formula | write it in the parameter's unit |
| `parameter X: range A to B step S goes nowhere` | low not below high, or a step of 0 or less | swap or fix the numbers |
| `parameter X: the range A to B is not a whole number of S steps` | the step doesn't fit the range | change the step or an end |
| `parameter X = V is not one of the range's values` | the value is outside the range or between steps | move the value, or widen the range |
| `the parameter test has no test X` | a typo in `tests=` or the mode | use ends, steps, extremes or random |
| `X: the sketch has N profiles and no profile= was given` | the step takes the first profile, and which one is first can change when a value changes | pass `profile=` that picks by a point inside or by area ([rules](../rules.md) 13) |
| `parameter X: nothing in the design uses it` | no feature or sketch dimension uses it, even through other parameters; Python may read its value, but Fusion never does | use it in a feature or dimension, or drop it. A favorite gets "its Customize slider does nothing" ([rules](../rules.md) 9) |
| `the design's units are not mm` | a bare number in an expression is read in the design's units | set mm at the start of `describe()`, as the template does |

### Messages from Fusion

| Message or symptom | Cause | Fix |
| --- | --- | --- |
| `No target body` on a pattern | the pattern's first copy misses every body | cut the pattern out of a big sheet body first (rule 21) |
| `All tool bodies are lost` | a later cut split a tool body in two | make the tool bigger than the part (rule 23) |
| a combine or chamfer breaks, or picks the wrong edge, when a count changes | a list of bodies or edges that grows with a parameter | pattern the feature and combine one fixed body (rule 24) |
| a round or chamfer loses its edges when a cut changes | it comes after the cut that changes | put edge features before such cuts (rule 30) |
| bodies named `Name (2)` | a cut split the part | use the biggest, report the rest as loose pieces (rule 25) |
| `multiple target` errors after many renames | editing in place can't match the steps | run `clean` (rule 27) |
| a sketch takes minutes, or holes come out solid | many overlapping copies in one sketch | draw one copy and pattern it in 3D (rule 29) |

### Messages from the tools

| Message | Cause | Fix |
| --- | --- | --- |
| `fix these first (or --no-check)` | precheck found problems in the code | fix them; `--no-check` only for a one-off rerun of an older script |
| `no new log line for N minutes. The last Fusion call started: ...` or `... Is Fusion up, ...` | Fusion is closed, the runner add-in isn't running, a dialog is open, or Fusion hangs | look at Fusion's window. A hung run stops only when Fusion quits; then close the `~recovered` tab without saving |
| `runner: <status>` and an error | the runner couldn't run the script | read the error; often a wrong path in the entry file |
| `the log does not end in DONE` | the script ended without finishing | read the log's last lines |
| `<NAME>.log` holds only a traceback | the entry file couldn't run `build.py` | a syntax error, or the entry file's `CODE` path is wrong |

## Faster iterations

Most of an iteration's time goes to waiting for a click, for a rerun after a typo, or for a step that
redraws more than it needs to. When a design costs time in a new way, add the fix here.

1. **Run through the runner.** `python3 <kit>/fusion/tools/fusion_outputs.py run NAME --mode saved` in a
   background shell. The CadApprenticeRunner add-in starts with Fusion and runs the script with no click
   on ▶, also behind a locked screen. It prints the log as it grows and exits 0 only on DONE. Once,
   a run sat 62 minutes behind a locked screen, waiting for the ▶ click. The click in
   fusion/rules.md § Running a script is the fallback for when the add-in doesn't answer.
   A stuck run can only be stopped by quitting Fusion. The runner then reports it as cut off and doesn't
   run it again. Fusion reopens the design as a "~recovered" tab, holding that run's half-done changes;
   the runner refuses to work while it is open, so close it without saving.
2. **Let the checks catch mistakes before Fusion does.** `prep` and `run` read the code first
   ([precheck.py](cad_apprentice/precheck.py)) and stop on a problem, in seconds
   instead of minutes into a run. When a run fails on something a check
   could have found (a typo in `uses`, a key built with `%` that read-ahead can't see), add that check
   to precheck.py with a case in [test_precheck.py](cad_apprentice/test_precheck.py).
3. **Pick the cheapest mode.** `saved` when parameters or a few steps change: only those steps and what
   `uses` them rerun. `clean` when most steps change or the order is wrong: updating every step in
   place is far slower than a rebuild. A refactor counts: once the suspension bridge, moved to helpers.py,
   sat over 15 minutes in its first sketch in `saved` mode, against about 6 minutes for a whole `clean`
   build. Before a run, ask how many steps the change touches. A slow step swapped for one under a new
   key counts too: `saved` deletes the old step only at the end, so the marker first computes it once
   more, on top of the new one. On the suspension bridge, two old one-way truss rows left in behind one new
   symmetric row held Fusion at full CPU for over half an hour. Suggest `clean` for that; a clean run
   deletes hand edits, so ask first ([rules.md](../rules.md) rule 4).
4. **Library methods, not custom steps.** A step written inside a design script has no test, and the
   next design copies it. Put it in the library instead ([Adding a step type](#adding-a-step-type)).
5. **One copy of each helper.** Before copying a function from another design script, move it into
   helpers.py. A copy that differs gets a parameter there, not a second version.
6. **Read the timings.** The log says "done in N s" after every Fusion call that took a second or more. Spend
   effort on the slowest steps, for example a big sketch that a small change redraws whole. Do it after
   every run, and change the design where it can be built more simply (fusion/rules.md rule 33).
   Those timings are for the script's calls. For how long Fusion takes to recompute each feature,
   `adsk.core.Application.get().executeTextCommand('fusion.DumpFeaturesByComputeTime')` returns one line
   per feature: design, feature, seconds, health.
7. **Keep the reruns small.** Small sketches (fusion/rules.md rule 14) and exact `uses` lists, so a change
   reruns only the steps that depend on it.
   A sketch with many lines and dimensions draws faster inside `with deferred(s):`, which holds
   Fusion's solve and profiles until the block ends. 60 dimensioned rectangles drew 2.7 times faster,
   with the same profiles. Read nothing inside the block that needs the solve, like
   profiles or where a point moved to.
8. **Ask for the screen once.** Full control and keep-awake at the start of the session, held to the end
   (fusion/rules.md rule 5). The runner needs neither to run a script; they are for clicks and checks in
   Fusion's window.
9. **Fix older scripts when you next touch them.** Scripts written before the checks can fail them, some with
   dozens of problems. Fix them on their next iteration, or pass
   `--no-check` for a one-off rerun.
10. **Make patterns cheap** (fusion/rules.md rule 32). Pattern the feature, not sketch geometry or bodies
    a combine then uses. Two rows out from the middle, one each way, become one symmetric pattern: on
    the suspension bridge that took a 295 s row to 0.1 s. Try `compute='identical'` on a slow pattern
    and keep it only if the volume and face count match Adjust's; it cut the floor ribs from 11.7 s to
    0.7 s. Never `'optimized'`: it gave a wrong part with no warning in 7 of 11 bridge patterns.
11. **Drop `was=` once the saved design has the new names.** When a step's spec changed, the library
    checks whether only renamed names differ by trying each of their old and new names. It tries only the
    names that step uses, but every one of them doubles the tries. Before that limit, the suspension bridge's 25
    renames meant 33 million tries for its main cable sketch, and the run hung until Fusion was quit.

## Adding a step type

1. Add the method to `__init__.py`. Most are a `make` function, an `update(feature)` function that
   edits in place, and a call to `self.step(...)`.
2. Put **every value it sets** in `spec`. A value left out is a change the library never sees: once
   pipe, hole, shell and scale ignored their own size changes until this was fixed.
   Every value in `spec` must either be set again by `update`, or be listed in `fixed=` so a change
   replaces the feature. A value in `spec` that `update` skips is logged "updated" and never applied:
   once a combine's operation stayed "join" for good this way.
3. No silent failures: when Fusion refuses something, raise with a message that says what and why.
4. Add the name to `STEPS` in [precheck.py](cad_apprentice/precheck.py), so its keys and `uses` are checked.
5. Add it to `test_features.py` (or a test of its own) with a first value and a changed one, and
   run that through the runner. The change must edit in place, or the log must say why it replaced.
6. Add a row to the [Supported steps](#supported-steps) table above, and to the plain list in the
   [README](../../README.md#supported-steps).
