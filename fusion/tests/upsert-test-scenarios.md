# cad_apprentice: full test plan

What the automatic tests for [cad_apprentice](../../README.md) must cover, written as plain
scenarios. Written after a large design showed the library breaks in ways the
28-check [test_components.py](test_components.py) never hit: reorder, regroup, renames, replace in the
middle. Built later, in an overnight session. Library work is kept apart from design work: no
scenario opens or changes a real design.

## 1. How the tests run without anyone at the screen

Today a run needs clicks in Fusion's Scripts dialog (fusion/rules.md § Running a script). That can't
run overnight. So the first job is a runner that needs no clicks.

**The runner add-in, `UpsertTestRunner`.**
- A Fusion add-in in the kit, `~/cad-apprentice/fusion/runner/`. The person adds that folder once with
  "+" in the Add-Ins dialog and ticks "Run on Startup". Nothing is written into `~/Library`.
- It watches a folder in the kit, `~/cad-apprentice/fusion/tests/run/requests/`.
  Claude drops a request file there from the shell: which scenarios to run (all, one group, or a list
  of IDs).
- A background thread sees the file and fires a Fusion custom event. Fusion API calls are only safe on
  the main thread, so the event handler runs the scenarios there.
- A "busy" flag: while a request runs, a new event is ignored. Fusion can deliver the next event
  inside `adsk.doEvents()`, which the library and design scripts both call, so one run could otherwise
  start inside another.
- On startup it waits until Fusion has finished starting and is signed in, then picks up any request
  that was left half done (a small state file says which scenario it reached).
- It writes a live log (LiveLog) and `result.json` at the end.
- **Is it alive?** The shell watches the age of the last LiveLog line, not a heartbeat. A heartbeat
  from the background thread keeps beating while the main thread hangs, and one from the main thread
  stops during a long step. The timeout is 15 minutes, longer than the slowest step of the
  biggest design built so far.
- After a hang or crash, Claude quits Fusion if it is still running, then starts it with
  `open -a "Autodesk Fusion"`. The add-in starts with it and carries on from the scenario after the
  one that crashed. The crash counts as a failure. A scenario that crashes twice is skipped. After 3
  restarts in an hour, the run stops and goes to the report.
- It reloads `cad_apprentice` and the scenario files from the repo on every request, so a fix needs no
  restart. A change to the runner itself does need a Fusion restart.
- Restarts can bring up dialogs no script can close: a Fusion update, sign-in, crash recovery. If
  Fusion doesn't answer 10 minutes after a restart, the run stops and goes to the report. Computer
  use is not a fallback overnight: a locked screen defeats it.

**Isolation.**
- Each scenario builds in a new, unsaved tab and closes it without saving. It never touches a tab it
  didn't open.
- A crash or a forced quit loses every unsaved tab, the person's too. So the person saves and closes their tabs
  before the run, and the runner refuses to start while a tab it didn't open has unsaved changes.
- **One saved design, no more.** A Fusion plan can have only a few slots for editable documents, so the
  whole night saves at most one new design: `fusion_upsert test design`, in a folder
  `fusion_upsert tests` inside Admin Project, never its root. Every scenario that needs a saved
  design (A6, D3, F4, K) reuses it: it opens that document, clears it (all
  features, parameters and components), builds, and saves a new version. Nothing is deleted. If it
  can't be created or saved (no slot free), those scenarios are skipped and listed in the report,
  and the run goes on.
- Tabs are tracked by their file id, not by position: a go-back (K4) closes a tab and opens a new
  one.
- Before and after each request, the runner lists open tabs and their modified flags. Any change to
  a tab it didn't open is a failure.
- Pictures, STLs and logs from a test go to `run/results/`, never to a design's own folders or the
  repo's `stl/`.

**The test model.** Small and fast, but with every feature type the library has:
- Two components, one nested inside the other, plus one in the top component.
- A box sketch and extrude, a second sketch that projects a tagged point from the first, a cut, a
  join with participant bodies, a symmetric extrude, a combine, a fillet with two edge sets, a
  chamfer, a rectangular pattern of a feature, a move, a base body and a construction plane.
- About 8 parameters, 3 of them favorites, some as formulas of the others.
- Each scenario writes the script as version 1, runs it, changes something (the script, or the design
  by hand through the API), runs version 2, then checks.

## 2. Checks that run after every scenario

These are general, so each scenario only adds what is special to it.

1. **Healthy.** No feature has an error or a warning, unless the scenario expects one.
2. **Same as a fresh build.** Build version 2 from nothing in a second tab and compare with the
   updated design:
   - timeline order and names
   - group names and their members
   - the component tree
   - body names and counts
   - volume of each body (within 1 part in a million) and its bounding box (within 1e-4 cm)
   - parameter names, expressions, comments and favorites

   This one check catches most reorder, regroup and replace bugs.
3. **A second run changes nothing.** Run version 2 again:
   - all counts are "same" (no created, updated, replaced or removed)
   - no save (checked only on a saved design; an unsaved tab has nothing to save)
   - the timeline is unchanged
4. **Hand work survives.** Every hand-made feature from the scenario is still there and healthy.
5. **No lost steps.** Every step the script visited still exists. Every feature without a key is one
   the scenario made by hand.
6. **The log is honest.**
   - The counts match the per-step lines.
   - Every change line gives a reason.
   - Nothing changed that the log doesn't name.
7. **Nothing else touched.** The open-tabs check above.
8. **Time.** Each run's time is recorded. A no-change rerun of the test model over 5 s is flagged.

## 3. Scenarios

IDs are for the results file and commit messages. **(bug)** marks a scenario that reproduces a bug
already seen. Those run first.

### A. First build and plain reruns
- **A1** Fresh build of the full test model: every check in § 2 passes.
- **A2** Rerun with no change: nothing created, updated, replaced or removed.
- **A3** Rerun after some groups are collapsed by hand: they are opened for the run and collapsed again.
- **A4** Rerun with the timeline marker rolled back: the run moves it to the end first, and nothing
  looks hand-made.
- **A5** The same step key used twice in a script: a clear error, and nothing in the design changed.
  A key written twice stops the run before its first step (precheck). A key chosen at run time
  stops at its second use, so the run goes back to the last save. Runs on the saved test design.
- **A6** Save, close, reopen and rerun: the keys survive the trip through the cloud, and nothing
  reruns.
- **A7** A tab that was never saved, with a hand-changed parameter: a run that changes a value, then
  a run that fails. Measured, not failed: what happened to the hand value, what the failed run said
  about going back, and whether the tab is still open.

### B. Parameters
- **B0** A `was=` rename where the new name already exists: a clear error, nothing lost.
- **B1** A new parameter is added with its comment and favorite star.
- **B2** The script changes a value: it is set and logged.
- **B3** A value is changed by hand: it is kept and reported. The script's value is not forced.
- **B4** It is changed by hand, then the script changes it too: the hand value is still kept, and both
  values are reported.
- **B5** Rename with `was=`: its value and every expression that names it carry over. Nothing is
  rebuilt.
- **B6** A chain of renames a → b → c, with the design still at a.
- **B7** The same chain, with the design already at b.
- **B8** A rename where Fusion respaces the expressions ("( a - b )"): the compare ignores spaces,
  so its value isn't flagged as changed by hand.
- **B9** A parameter dropped from the script is removed. Also: a script that drops all its parameters
  at once. Today that removes none.
- **B10** A dropped parameter that something still uses: kept and reported. It goes on a later run,
  once nothing uses it.
- **B11** A dropped parameter that only a hand-made feature uses: kept, never deleted.
- **B12** A favorite given a formula: the run stops with an error naming it, before it changes anything (it used to be only a log warning).
- **B13** The comment or favorite flag changes: it is updated in place. On a saved design it must
  also be saved; today that change alone doesn't trigger a save.
- **B14** A name Fusion refuses (`floor`): a clear error naming it.
- **B15** A unit change (mm to deg): a clear result, either set or refused with a message. Never
  silent.
- **B16** 21 renames at once, with one step's spec changed too: done in under 2 minutes and the
  changed step reruns. Matching renamed names used to try every mix of them, 2 million for 21.

### C. A step's spec changes
- **C1** Each feature type, one change at a time, is edited in place, not replaced:
  - extrude: distance, symmetric distance, operation, profile picker, participants, body name
  - combine: target, tools, operation
  - fillet: radius, edges
  - chamfer: distance, edges
  - pattern: counts, spacing, adjust
  - move: x, y, z (no in-place update today, so it is replaced)
  - plane: offset (edited in place when `make` has an `.offset()`, since 6a77b91c; a plane without
    one is replaced)

  **(bug)** for extrude participants and body name, and combine target and tools: those lambdas
  aren't in the fingerprint, so today a change to them does nothing. The same holds for move bodies,
  pattern bodies and axes, and the plane's `make`. Adding an in-place update for move is approved
  (§ 6): after it, move edits in place like the rest.
- **C2** A sketch's draw function changes: the sketch is redrawn and its extrude repointed.
- **C3** **(bug)** A helper that a draw function calls changes, but the draw function itself
  doesn't. Today the fingerprint hashes the draw function's own code only, so nothing reruns.
  Expected: it reruns, or the README says plainly that helpers go in `spec=`.
- **C4** **(bug)** A value a lambda reads from outside changes: a captured variable or a global
  (`lambda: comp.xConstructionAxis if AXIS == 'x' else ...`, with `AXIS` changed). Today the
  fingerprint hashes the code and names, not those values. Expected: it reruns, or the README states
  the rule. (Switching the code itself from the x axis to the y axis is already caught, since names
  are hashed.)
- **Fingerprint fixes are approved, with no migration.** A fix to C3, C4, C8 or J2 may change what
  goes into a fingerprint. Existing designs then rerun or rebuild their steps on their next run;
  that is fine, no backward compatibility needed.
- **C5** A comment-only change or a moved line: nothing reruns.
- **C6** `uses=` changes: the step reruns.
- **C7** A step rerun makes the steps that use it rerun too, and theirs in turn.
- **C8** A step's label changes in the script but nothing else: today the name isn't in the
  fingerprint, so the feature keeps its old name. Expected: it is renamed in place, nothing rebuilt.

### D. Sketch redraws
- **D1** A redraw repoints its extrude, and the old sketch is deleted.
- **D2** A redraw of a sketch another sketch projects from (`tag()` / `tagged()`): both still
  resolve.
- **D3** A redraw that breaks a hand-made fillet: BROKEN in the log, and the design goes back. Needs a
  saved design; an unsaved tab only logs "never saved". A STOPPED that names the fillet passes too:
  the library now stops before it deletes a step the fillet hangs on.
- **D4** A redraw inside a nested component stays in that component.
- **D5** Several retired sketches are deleted last-first, with no projection errors.
- **D6** A run that dies mid-redraw leaves a "(old)" sketch. The next run cleans it up.
- **D7** A sketch put on another plane, same key and same `uses`: redrawn there. Added
  when the library first checked the plane. It fails with the check switched off.

### E. Order and reorder
- **E1** The script moves a step later: it is moved, not rebuilt. Same as a fresh build.
- **E2** The script moves a step earlier.
- **E3** **(bug)** The script moves a block of steps (for example a chamfer and a fillet moved
  before two pattern cuts). Expected:
  - the later steps move after them, not one replace after another
  - no step is lost
  - the log lists the moves
- **E4** **(bug)** The call that moves a step: `TimelineObject.canReorder` and `reorder` take an
  index. The library passed a timeline item, so every move failed and fell back to a replace. Fixed,
  and this scenario proves it.
- **E5** A move Fusion refuses, because the step depends on something that would then come after
  it. Expected: rebuilt at its new spot without losing what's after it, or a clear refusal. Never a
  quiet loss.
- **E6** Two independent steps swap places.
- **E7** A step moves from one group to another.
- **E8** A move with a hand-made feature between the old and new spots: that feature stays put and healthy.
- **E9** A move while groups are collapsed.
- **E10** A step moved into another component: refused with "Move it by hand first" (covered
  today; keep it).
- **E11** A step moved to the very end. Today, when the step before it is the last item, the
  library can't move it there and replaces it instead. Expected: moved.
- **E12** Many renames and moves in one run (Fusion's "multiple target" errors, fusion/rules.md):
  same as a fresh build.

### F. Adding and removing steps
- **F1** A step added in the middle lands at its spot, before the steps after it.
- **F2** A step added at the very start.
- **F3** A step removed from the middle, along with the steps that used it.
- **F4** A step removed that a hand-made feature uses: BROKEN, and the design goes back. Needs a saved
  design.
- **F5** A whole component removed: its steps and occurrence go (covered today).
- **F6** A key reused with a new meaning: `body()` gives its clear message.

### G. Replace, and what depends on it
- **G1** A replace at the end of the timeline works.
- **G2** **(bug)** A replace in the middle deletes the keyed steps built on it, and the steps the
  script already passed don't come back that run. Today `finish()` now reports "deleted with a step
  it used". Expected: the library either rebuilds them in the same run, or refuses before deleting.
  Never leaves a hole.
- **G3** A replace with a hand-made feature after it: refused (covered today).
- **G4** **(bug)** A fillet with two edge sets, updated after its body changed: "invalid argument
  index". Reproduce it, then fix it so the fillet edits in place. Fixed: the set's
  parameters are read after its new edges are set. Tested in `test_edit_in_place.py`.
- **G5** A combine given the same bodies again: no refusal and no replace (fixed; keep a
  test).

### H. Groups
- **H1** One group per component, named after it.
- **H2** A `group()` inside a component is named "Component · group".
- **H3** Loose steps of a component sitting between its groups: today the groups overlap and one is
  skipped. Expected: a clear log line, or the library sorts it out.
- **H4** A step that moves between groups: both groups' members update.
- **H5** A group renamed in the script: renamed in the design, steps untouched.
- **H6** A group dropped from the script: its steps stay, ungrouped.
- **H7** Groups collapsed by hand stay collapsed after the run, also after a run that regroups. Today
  regrouped groups come back open.
- **H8** A group made by hand is left alone.
- **H9** A group of one step: no group, and no error.
- **H10** **(bug)** Regroup when a group's step was deleted during the run: today this crashed with
  `'NoneType' object has no attribute 'index'`. Fixed by skipping lost steps.
  It must also finish with no BROKEN: a step deleted along with a dropped one is
  made again in the same run (before, every rerun was BROKEN).
- **H11** A rerun with no change doesn't touch the groups at all.

### I. Components
- **I1** Nested components: covered by every scenario (Inner sits inside Outer) and by `test_components.py`.
- **I2** A component renamed in the script: the name changes, nothing is rebuilt.
- **I3** A Part-intent design: everything stays in the top component and the log says so.
- **I4** Copies of a component placed by a pattern (a preview copy): the copies follow when the
  count or spacing changes.
- **I5** Joints between components: covered by `test_joints.py`.

### J. Hand edits to the script's features
- **J1** A feature is renamed by hand: the key still finds it, the new name stays, and the run reports it. The
  script's name doesn't come back.
- **J2** A keyed feature is changed by hand (an extrude's distance): before, the fingerprint was the
  same, so the change stayed and nothing said so. Expected: the hand value stays and the run reports it,
  like a hand-changed parameter.
- **J3** A keyed feature is deleted by hand: the run makes it again.
- **J4** A keyed feature is suppressed by hand: reported, not silently unsuppressed.
- **J5** Hand-made features are added after and between the script's: they stay and stay healthy.
- **J6** `take_over`: a feature that lost its key and was renamed by hand is taken over by the script.
  Nothing is created or replaced, and it gets back the script's name, its key and a fingerprint.

### K. Saving and going back (saved design in the test folder)
- **K1** A run that changes nothing saves nothing.
- **K2** A run that changes something saves once, with the note.
- **K3** Unsaved changes at the start: a restore point is saved first.
- **K4** A BROKEN run goes back to the last saved version, and nothing else is saved. A STOPPED
  run goes back the same way and passes too (see D3).
- **K5** The go-back waits for the restore point to show up in the cloud. Pass: the version it
  reopens is the restore point, not the one before it. Covered by K4 and K9.
- **K6** An exception mid-run: `abort()` logs STOPPED and goes back.
- **K7** Known limit: opening and closing groups marks the tab as changed. Measure it on a no-change
  rerun: record whether the tab is marked changed. Reported, never a failure.
- **K8** A go-back that fails (the tab refuses to close): the run logs COULD NOT GO BACK, keeps its
  own error, and marks the design with the last good version. The next run here saves no restore
  point; when it fails too, it goes back to that version. A run that works clears the mark.
- **K9** Unsaved hand changes, then a run that stops before its first step: the restore point is
  saved before anything changes, and the go-back reopens it with the hand change in it.
- **K10** A clean rebuild (`wipe`) that fails: it goes back to the version before the wipe, not to an
  empty design.

### L. Parameter trials (robustness)
- **L1** Each favorite at its low and high values: no warnings or errors.
- **L2** A trial, then the value put back: the design matches what it was (volume, health). Tests
  the "split body" known limit.
- **L3** A pattern count changes, and a fillet after it keeps its edges. Rounds on the pattern's own edges go in the pattern with the cut: after it, a hole
  that goes takes its edge, and Fusion warns. That shape is flagged as a known limit, not failed.
- **L4** The library's parameter test, `Builder.trials()`, with no ranges: every plain-value parameter a step down
  and a step up (14 trials on the test model), no formula tried, the design as it was after. Then
  `only=` and `values=`, and a name the design doesn't have is refused.
- **L5** Parameter ranges and the test's stages. `param(range=, step=)` saves the ranges in the
  design. ends: hole_n at 2 and 6, round_r at 0.5 and 20 mm; the 20 mm round fails, so the test
  halves the gap to the largest round that works, reports the range as too wide and skips the later
  stages. Then steps (one step either side), extremes (all low, then all high, which fails and logs
  the set, then all high again set from all low, which fails too) and 3 random sets with a logged seed. A range on a formula is refused, and a later Builder
  reads the ranges back from the design.
- **L6** `Builder.back_to_saved()` after a trial: the value is back, but the tab still counts as
  changed. It closes the tab without saving and opens the saved version: one tab of the design, the
  same version, nothing unsaved, the design as it was.

### M. Logging
- **M1** Every LiveLog line has a time and is written right away.
- **M2** The last line before a crash names the step it was in. Tested with a step that raises an
  exception, not a real crash; there is no safe way to crash Fusion on purpose.

## 4. Order for the overnight session

0. Before the person goes to bed: ask everything in § 6 in one go, and check the setup in § 5.
1. Build the runner add-in and prove it with one scenario (A1), while the person is still up: they add it
   in the Add-Ins dialog and ticks "Run on Startup". If A1 can't run without clicks, the night is
   not started.
2. Build the checks in § 2, starting with "same as a fresh build".
3. Run the **(bug)** scenarios: E3, E4, G2, G4, H10, C3, C4. Then C8 and J2, the quiet gaps.
4. Run the rest by group: A, B, C, D, E, F, G, H, I, K, L, M.
5. Run a real design's own tests, if the night has one, once A to M pass, fixing design failures
   as they come.
6. For each failure:
   - fix the library, or the design for a design failure
   - rerun A to M, so a fix doesn't break something else; a real design's tests rerun once, at the end
   - commit each fix on its own, naming the scenario ID, with only the files the fix changed
   - never change what a scenario expects just to make it pass; if an expectation was wrong, write
     down why in this file
   - fingerprint changes and a move in-place update are approved (§ 6); any other change to
     the library's API is written up, not made
7. **Stop by 6:45** and push, before any morning routine that commits too. Work not done by then goes in the report as open.
   If the last pull has a conflict, the commits stay local and the report says so.
8. The morning report, `run/results/report.md`: scenarios passed or failed, fixes made (with
   commits), a real design's results and questions, and anything still open. Its summary is also the session's last message.

**The 3MF scripts** have their own plan, [3mf-test-scenarios.md](../../3dprinting/3mf-test-scenarios.md).
They need no Fusion, so they run while Fusion is busy, or first if the runner
isn't ready. Their permissions and questions are asked with § 6.

**Time budget.** The night is about 8 hours. Rough shares: runner and checks 1.5 h, A to M with
fixes 3 h, a real design 3 h, report and push 0.5 h. The report says where it stopped.

Each scenario's result goes in `run/results/` next to this file, with a summary table at the top of
the morning report. Nothing in `run/` is committed.

**Files left alone.** The working tree may have other uncommitted changes, such as a tuned
`.3mf`. The session never
stages, commits, reverts or deletes them. Another session may be
working on a design at the same time: pull before each design fix, and commit only the files the
fix changed.

## 5. Setup to check before the run

The person does these before bed. The session checks each one it can and says which it can't.
- **Save and close every Fusion tab.** A crash loses every unsaved tab.
- **Power plugged in, lid open.** The session runs `caffeinate` (or the app's keep-awake) for the
  night.
- **Fusion up to date and signed in,** so a restart doesn't stop on an update or sign-in screen.
- **Bambu Studio quit.** `update_3mf.py` refuses to run while any Bambu Studio is running
  ([3MF plan](../../3dprinting/3mf-test-scenarios.md) § 1).
- **No scheduled task opens Fusion or Bambu Studio before 7:00.** The session checks the scheduled
  task list.
- **The runner add-in on** with "Run on Startup" (step 1 of § 4).
- **How the session starts.** The repo's settings refuse anything not on an allow list
  (`"defaultMode": "dontAsk"`), and a scheduled task also goes through the guard hook
  (`scripts/routine/unattended_guard.py`), which refuses Monitor, long sleeps, writes outside the
  repo and scripts in the kit folder. So the night runs as a chat session the person starts, not a scheduled
  task. A "yes" in chat doesn't add allow rules, and anything off the lists is denied without a
  prompt, so the session runs in **bypass permissions** mode; the limits in this plan
  (§ 1, § 6) are then the only guard.

## 6. Permissions and questions, asked at the start

Asked together, before the person goes to bed, so nothing waits on them at 3 am.

**Permissions.** Covered at once by bypass permissions mode (§ 5); without it, each needs an allow
rule.

| What | Why |
|---|---|
| Edit and create files in `~/cad-apprentice/**` and this plan | The runner, scenarios and library fixes |
| `python3` without the `cd` prefix | Checks, the 3MF tests |
| `mkdir`, `cp`, `rm` and request files under `~/cad-apprentice/fusion/tests/run/` only | Talking to the runner |
| `ps`, `pgrep`, `stat`, `tail` | Is Fusion alive, how old is the last log line |
| Background wait loops (`while … sleep`) or the Monitor tool | Waiting for `result.json` |
| `open -a "Autodesk Fusion"` | Restarting after a crash |
| Quitting Fusion (`osascript -e 'quit app "Autodesk Fusion"'`, then `killall` if it hangs) | Getting out of a hang. Kills unsaved work, hence § 5 |
| The app's keep-awake, or `caffeinate` | Stop the Mac sleeping |
| Reading `~/Library/Logs/DiagnosticReports` | Finding why Fusion crashed |
| Committing each fix and pushing at the end | Saving the fixes |
| Subagents | Reviews, such as an outsider's read of new names |
| Creating the `fusion_upsert tests` folder in Admin Project and one design in it, saved again and again; opening and closing its tab | A6, D3, F4 and K. Uses one editable-document slot. Nothing is deleted |
| The 3MF plan's permissions ([3mf-test-scenarios.md](../../3dprinting/3mf-test-scenarios.md) § 5) | The 3MF tests |

Not needed: computer use (the runner needs no clicks, and a locked screen defeats it), writing into
`~/Library/Application Support`, messaging apps.

**Questions.** Answered before the first night, except where it says default.

| Question | Answer |
|---|---|
| **J1:** a feature renamed by hand | The new name stays, and the run reports it |
| **J2:** a script's feature changed by hand | The hand value stays, and the run reports it |
| May fixes change what goes into a fingerprint (C3, C4, C8, J2)? | Yes. No migration: existing designs may rebuild on their next run |
| May the night add an in-place update for move (C1)? (Plane has one already.) | Yes |
| Which design gets the one save? | The test design. The person's own designs aren't opened or saved |
| Branch | `main` |
| Project for the test folder | Admin Project, in a subfolder, never the root |
| Commits | One per fixed scenario ID, pushed at the end |
| Stop time | 6:45, before the 7:00 morning routine |
| How permissions are granted (§ 5) | Bypass permissions mode |
| 3MF B18: add a filament per part (`--filament PART=N`)? | No; every part stays on filament 1 |
| A label change in the script (C1, C8) vs a hand rename (J1) | Default: the library stores the last name it set; a feature whose name differs from it was renamed by hand and keeps that name |
| A trial leaves the unsaved tab broken for good | Default: close it, rebuild in a new tab, list it |
| Pull conflict at 6:45 | Default: commits stay local, listed in the report |

## 7. Open items

- **"(1)" names.** An old commit had steps named like today's ones under other keys. Today's are
  made while the old ones still exist, so Fusion names them "(1)", and the name stays after the old
  ones are deleted. **Proposed fix, not made:** after the end-of-run deletes, rename any step made
  this run whose name isn't its step name.
- **"(old)" sketches not deleted.** In some old commits, "(old)" sketches stay in the timeline
  although the log says they were deleted. `_remove_retired` doesn't check what `deleteMe()`
  returns, so a refused delete passes without a word. Why Fusion refused isn't known. **Proposed
  fix, not made:** check the delete's result, warn when it fails, find out why.
