# Fusion 360

These rules apply to every CAD job in Fusion, for any project. A project README can
add facts, but it can't drop a rule here.

**Before you write or change a build script, read [lib/README.md](lib/README.md):** the library's
steps, how a run works and how to read a failed one. To add a step or a helper to the library, follow
[the skill's Evolving the library](../skills/cad-apprentice/SKILL.md#evolving-the-library).

## Working with the person

1. **Be autonomous.** Work out what you can and write down your assumptions. The person can confirm them later.
   Don't ask about the obvious next step of a request. Do it. Asked to check where the original has
   fillets, add them too.
   - **Don't stop for a go-ahead on your own plan.** When the person asks for a change and you've
     worked out how, build it, test it and show the results. Pictures and a proposal come with the
     work, not instead of it (user, 2026-11-16: "more autonomy, please").
   - **Sort out the runner with other sessions yourself.** When another session needs Fusion, agree on
     who goes first. When Fusion hangs inside a run (high CPU, the log stopped for many minutes),
     force-quit it, start it again and tell the other sessions, without asking the person
     (user, 2026-11-16).
2. **Sketch before CAD.** Before building anything, show a picture of how you understand the task and
   ask only the most important questions.
3. **Do it all yourself in Fusion.** You have standing permission to control Fusion, including its
   Scripts dialog. Don't ask the person to click.
4. **Never edit or save another design without being asked.** Open tabs can hold the person's unsaved work.
   A new design you built yourself is different: save it when the work is checked, without asking.
   **Build a new design once, then iterate in it.** After the first save, every run updates that same
   saved design (the script's `saved` mode) and saves a new version of it. Never make another copy
   per iteration. The full checks of rule 7 run in that saved design too. If the script has moved on too
   far for an update, empty that design and build it again in the same document, as long as the script
   made everything in it. The old version stays in its history. The template's `clean` mode
   does this (`cad_apprentice.wipe`): it wipes the whole timeline, builds again and saves a new version, which is faster
   than updating every step.
   **Suggest a clean run after a large change.** When a change is big or slow to update in place
   (many new or renamed parameters, a step order that moved, a run that hung on an edit), weigh a
   `clean` run. First check that the person didn't change the timeline by hand: a feature, sketch or
   body the script didn't make, or a hand edit to one it did. A clean run deletes those. If you see no
   such risk, suggest it to the person. Don't run it without asking, and don't suggest it for small
   changes or on every round (user, 2026-11-16).
   **Editable documents are scarce.** A personal Fusion plan has only a few slots for editable documents, so
   every new saved design uses one up. A test run saves at most one new design and reuses it. A
   `night` run saves none: it leaves its tab open for the person to save by hand.
5. **Keep the screen free.** The person works on the same computer. Use background clicks first. If one gets
   refused, click yourself, then stop acting at once, so the screen is theirs until the next click. Don't act while a script runs. Run as
   few iterations as you can. **Ask for full control once, before the first run, and hold it the whole
   session. Never call `release_full_control`.** It clears the approval, so the next click asks Allow
   again, and the person has to click Allow over and over. One approval lasts until the
   session ends. Once it was released mid-session, and a later run then sat 62 minutes behind
   a locked screen before anyone could click ▶. Ask for keep-awake (`request_keep_awake`) at the same
   time, so the laptop doesn't sleep between iterations. Your screenshots also hide other open apps such as
   chat apps, and they stay hidden, so show them again after each iteration.
6. **Show pictures with every iteration.** Each iteration comes with renders that show the feedback was handled,
   and sketch pictures when sketches changed. Text doesn't work as well as visuals for these tasks. When
   the design comes from the person's photos, overlay it on them to check the angles.
   **Then stop and wait for the person's verdict on the design.** No STL for printing, no `.3mf`, no test-print
   offers and no commit until the person says the design is right. The first build is a draft for them
   to judge.
   **Draw details the way the person's sketch draws them.** A hook, barb or tab copies the shape in
   their sketch, not a generic shape of your own; and keep the part symmetric across its depth unless
   they say otherwise. Once, a feature pushed to one face for easy printing broke both.
   **Round the corners where it makes sense, inner ones too**, from the first build.
   An outside corner gets the inside round plus the wall, so the wall stays even. Points meant to be
   sharp stay sharp.
7. **Check lightly each iteration, fully at the end.** During an iteration, check only what the iteration changed.
   When a piece of work ends, run the full set: rerun
   the script to see nothing changes, then try each plain-value parameter and put it back. If the shape shouldn't
   have changed, compare volume, face count and size before and after. Save before the trials, stop at
   the first trial that doesn't come back, and go back to the save then, so a broken trial never gets
   saved. The template's `check` mode does all this in the saved design, and `night` in a
   fresh build that it never saves.
   **The full set takes a while, so it doesn't run on every iteration.** A normal build only builds, saves and exports.

## The design

8. **Name everything.** Sketches, extrusions, fillets, bodies, components, and everything else in the
   timeline get a name a person can read, like "Mouth corner round", not "Fillet3". Rename the person's
   features only if they ask.
9. **Use named parameters.** Thicknesses, dimensions, and angles are named parameters whenever possible,
   not numbers typed into a feature.
   - **What people tune is a favorite, and a favorite is a plain value, never a formula.** MakerWorld's
     Customize shows only favorites, and a formula there doesn't work. So a size like `16 * step_h`
     gets its own count, `step_count = 16` (a favorite), and `total_height = step_count * step_h`
     stays a formula. Fixed standards, like a thread pitch, are not favorites. Use `b.param(...,
     favorite=True)`; a favorite with a formula stops the run before anything changes.
   - **A detail scales with its parent; tune its share, not its size.** A curb is a share of the slab
     it sits on, a flute a share of the strut it's cut in. Then a bigger tower doesn't keep tiny
     fixed-mm details. Only the overall sizes the person picks (height, width, length, clearance) are
     in mm (user, 2026-11-16, suspension bridge).
   - **Watch for parts that get too thin, don't block them.** Shares times small parents can end up
     thinner than about one printed line (about 0.45 mm on a 0.4 mm nozzle,
     [Prusa](https://help.prusa3d.com/en/article/modeling-with-3d-printing-in-mind_164135/); the log
     warns below 0.4 mm). That can be fine, so log it as a warning after each
     build and test trial, with the thinnest size per trial, and don't fail the run (user, 2026-11-16).
   - **Keep a derived value off 0 with `max(1; …)`,** with the unit for a length (`max(1 mm; …)`). A
     `min` cap does the same job at the top. Never clamp a value the person typed in.
   - **A switch is a 0/1 parameter with no unit, used through `if()` inside Fusion expressions only**
     ([Autodesk help](https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-MODIFY-PARAMETERS.htm)).
     Python never reads it, because Customize doesn't run the script. It can't suppress a feature.
   - **Every parameter is used.** `finish()` warns about any parameter no feature or sketch uses, even
     through other parameters: changing it does nothing, so the parameter test proves nothing. A
     favorite that only Python reads gets a louder warning, because its Customize slider does nothing.
   - **Make the favorites ready to publish from the start.** MakerWorld's Customize lists them
     as they are, with no way to change it:
     - **Order: most-used first.** It shows favorites in the order Fusion made them. So the build script
       makes them in a fixed list: overall size first, then the other big parts, then small details,
       then print fit last. Add a new favorite at its place in that list, not at the end (`FAV_ORDER`
       in the template's build.py).
     - **Name: short plain words.** It shows the name as the label, underscores as spaces: `tower_height`,
       `peg_fit`, not `tower_total_height_mm`. Unit and detail go in the comment, which shows under it:
       write it for an outsider (what it changes, its unit, which way is tighter). Notes for us (who
       measured it, when, why) go in code comments.
     - Fixing either later means a clean rebuild that re-creates the favorites
       (`cad_apprentice.order_favorites()` with `OLD_NAMES`), a new `.f3d`, and a swap on the draft.
   - **Other names are long and say whose and what.** A name says which part or body it belongs to and
     what it sets: `test_plate_pegs_length`, not `pegs`. Long is fine.
   - **Check the names as an outsider after each design iteration.** Dump the parameter table (name, value,
     formula, comment) and have a fresh subagent, with no context, say which names it can't explain.
     Rename those before calling the iteration done.
   - **No trademarks in names:** not in parameters, their comments, components, bodies, features, the
     design, plates or print files. Name the thing, not the brand.
   - **When the person's words fit more than one parameter, name the one you'll change** in the status line
     before building. "Height" can mean the whole part or one feature on it.
   - **Never guess a tolerance.** A print-fit shrink, grow or clearance starts at 0, the true spec size.
     Set any other amount only from a number the person gives or one a test print measured. If a fit
     seems to need slack, ask them how much.
10. **One timeline group per component.** Each component's steps sit together in the timeline under a
    group named after it. A long component splits into several groups side by side, named
    `<Component> · <what>` (`Frame · legs`, `Frame · lattice`). Fusion has no group inside a group: the
    API refuses it with `InternalValidationError`, so the prefix does the nesting.
11. **Print-ready edges.** An edge that sits on the build plate gets a 45° chamfer, not a round. A
    round there starts as a flat overhang. Put the chamfer in the timeline before the fillets. Rounds
    on vertical edges print fine ([Makers Muse](https://www.youtube.com/watch?v=XTvBOGgx48I)).
12. **Work in components, and build one component at a time.** Do no work in the top component if the
    design allows subcomponents. Sketches, features and bodies go in a subcomponent, and each distinct
    part gets its own where that makes sense. The library does this with
    `b.component()`.
    - Finish one component before starting the next, so the timeline reads as a clear sequence: all of
      the frame, then all of the beam, and so on.
    - Place components against each other with joints, not by moving them by numbers. A joint keeps
      the parts together when a size changes.
    - Make copies of a component with a pattern (rectangular, circular, along a path) where one fits,
      not one by one. The count and spacing are then parameters.
    - **Variants are copies of one base part**, made in the timeline and then changed, not drawn
      again. Tuning the base then reaches every variant. A variant is a `b.copy()` of the base body,
      made inside the target component's `b.component()` block, then changed there; it still follows
      the base. Never make a variant from a second instance of the same component: editing one
      instance edits them all ([forum](https://forums.autodesk.com/t5/fusion-design-validate-document/break-link-between-copied-and-pasted-components/m-p/9806684),
      [forum](https://forums.autodesk.com/t5/fusion-design-validate-document/timeline-capture-joint-vs-move-component-origins/m-p/13405938)).
      Instances and patterns are only for parts that stay identical.
    - **Model half of a symmetric part and mirror it as the last step of that part's component,**
      but only where a symmetric extrude or pattern doesn't already do it; those are cheaper
      ([forum](https://forums.autodesk.com/t5/fusion-support-forum/slow-performance-and-using-components/td-p/9982720)).
    - **One drawing per kind of joint.** Every part that joins another uses the same drawn joint,
      test pieces included, so there is one fit to tune and one place to fix it.

## Test prints

**Think about test prints while you design.** It's a general rule for modelling and 3D printing. Each iteration, look for what could
    fail on the printer or not fit:
    - fits and tolerances: studs, sockets, slots, snap fits, holes for pins or screws, a part that
      must hold another;
    - thin walls, small ledges, sharp overhangs and long bridges;
    - small, detailed or unusual features.

    For each one, suggest a small test-print part that prints in minutes and tests only that one
    thing. **Suggest it; the person decides** whether to design it. Test pieces print in the same filament
    as the real part ([3dprinting/rules.md](../3dprinting/rules.md) step 3), and what a test print shows goes
    into the project README.

    **When the right value isn't known yet, offer a calibration piece:** one print
    that tries several values of one parameter side by side, so a single print picks the value. Mark
    each value so it can be told apart on the print, and keep the parameter in the model until the
    person picks. Offer it when it's relevant, not every iteration; the person decides.
    For a fit, print it twice: a coarse row of offsets, then a fine row around the best one. A
    two-part fit doubles the error: 0.35 mm on each part makes a 0.7 mm overlap
    ([Practical Alchemy](https://www.youtube.com/watch?v=Re4tKegVfqs)).

## Sketches

13. **A sketch is fully constrained and says what matters.** Nothing can move by accident, and someone
    reading it sees the design: what's concentric, the distance between the lines and curves that count,
    the thickness. Geometric constraints come first (concentric, tangent, parallel, equal, collinear).
    Then a few dimensions between real lines, each a size a person would name. No position formulas like
    `200 mm + center_u`, and no helper parameters that exist only to place points.
    A dimension that can reach 0 can flip; see "A distance dimension has no sign" under Fusion facts
    that cost time. For an offset that can be +, 0 or −, measure it from the far face as width ±
    offset, so the dimension never reaches 0 ([forum](https://forums.autodesk.com/t5/fusion-design-validate-document/best-practices-for-robust-parametric-designs/td-p/9112280)).
    - **No sketch fillets.** Round corners with a fillet feature
      ([forum](https://forums.autodesk.com/t5/fusion-design-validate-document/understanding-fusion-360-bottlenecks/m-p/6467830),
      [video](https://www.youtube.com/watch?v=zLL6foqTdJg)).
    - **A new hand-shaped curve that must scale uses a control-point spline** with evenly spaced
      points, as few as hold the shape (it usually needs more than a fit-point spline). A fit-point
      spline with hand-set handles is hard to keep in shape
      ([Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/sketch-control-point-splines-faq/),
      [forum](https://forums.autodesk.com/t5/fusion-design-validate-document/parametric-design-and-workflow/m-p/11591521)).
      Existing curves stay as they are.
    - **Pass `profile=` when a sketch has more than one profile.** Without it the library takes the
      first one and logs a warning. Pick by a point inside or by area.
14. **Keep sketches small.** As a rule of thumb, not a hard requirement, a sketch has few
    non-construction elements, ideally one profile or one continuous line. A small sketch is cheap to
    redraw, and parameters cover most changes without any redraw.
    A build ends with every sketch hidden. A very flat arc has its centre point far from the model, and a
    visible sketch with such a point makes Fusion zoom out to it and ruins navigation.
15. **Sketches are redrawn whole, not updated piece by piece.** Matching a sketch's lines one by one is
    too hard, so the library doesn't try.
16. **A redraw can break the person's features.** It gives every face after the sketch a new identity, so a
    feature the person made by hand on those faces breaks. The run then stops, closes without saving and reopens
    the last saved version. To change such a sketch, use one of these:
    - Keep the curves and change only the dimensions and constraints, in a one-off script. Faces keep
      their identity, so a hand-made fillet on them survives.
    - Change it by hand.
    - Remove their feature first, if they agree.

## Build scripts

17. **Build scripts use the shared library,** [`lib/cad_apprentice/`](lib/cad_apprentice/).
    The script says what should exist, and the library creates, updates or leaves each thing alone, so
    this logic is written once. How it works is in [lib/README.md](lib/README.md).
    **Improve the library as you go, on every design.** When a design needs a feature
    type, a helper or a check the library doesn't have, add it to the library, not the design script
    ([the skill's Evolving the library](../skills/cad-apprentice/SKILL.md#evolving-the-library)). A design script holds
    only that design's shapes and sizes. How to keep runs fast is in [lib/README.md § Faster iterations](lib/README.md#faster-iterations).
18. **Scripts can be rerun safely, and they keep the person's work.** Running a script again on the
    same design gives the same result and leaves anything the person added in place. Why: deleting a feature from the middle
    of the timeline makes later features crumble. So a script changes things in this order:
    - change named parameters, which leaves the timeline alone;
    - edit a feature where it is: roll back to it, change it, roll forward;
    - insert a new feature at its spot the same way;
    - delete a feature only when it can't be edited, and only one the script made.

    Afterward it checks every feature, including the person's. If one broke or went missing, it closes
    without saving, reopens the last saved version, and reports what broke. If the person changed a
    parameter by hand, the script keeps that value and says so.

**Long scripts log as they go.** Write each line to the log file the moment it
happens, with the time, using `cad_apprentice.LiveLog(path)` as the log list. Then a run can be watched
with `tail -f` and a slow run told apart from a hung one. A log written only at the end left a
15-minute trial run with no way to see progress.

- **Say what's next before each slow step**, with `cad_apprentice.progress(log, 'trial x = 2: starting')`.
  The library already does this for every step it builds. When Fusion freezes or crashes, the last
  line names the step it died in, and the lines above show what got done.

**A log line around every slow call.** Any Fusion call that can take long goes inside
`with cad_apprentice.slow(log, 'what'):`. It writes "what" before the call and "what: done in 4.2 s" after,
so a run that hangs names the exact call, and a slow one shows where the time went. Slow calls: setting
a parameter or a dimension, `adsk.doEvents()`, rolling or moving the timeline marker, adding or deleting
a feature, `save`, `saveAs`, closing or opening a document, exporting, saving a picture.
`cad_apprentice.set_param(log, p, expr)` and `cad_apprentice.catch_up(log)` do the common two in one line.
Without these lines, a test row that once sat for 4.7 hours left one line in its log, the row's
name at 05:57, and nothing told which of its parameter sets Fusion was stuck in.

- The library does it for every step, and for every slow call of its own.
- [check_slow.py](lib/cad_apprentice/check_slow.py) lists slow calls with no `slow()` around
  them: `python3 projects/hobby/cad-apprentice/fusion/lib/cad_apprentice/check_slow.py <file or folder>`. A hook runs it after every
  Edit or Write of a Fusion script, so a missing line shows up at once.
- A call that's fine without one says why in a `# slow-ok: <why>` comment, on its line or on its
  function's `def` line. Example: a sketch's draw function, which the step's own "make" line already
  covers. Put the comment there rather than wrapping code inside a step's draw function: wrapping changes
  the step's fingerprint, and the next run would rebuild it.
- Scripts from before this rule may still have calls without one.
  Fix them the next time a script is edited; the hook will list them.

**No silent failures anywhere.** This goes for the library and for every Fusion script.

- Something wrong stops the run with an error that names the step and what's wrong. Example: a step
  whose `uses` names a step that doesn't exist, or comes later, stops the run. Before, it was skipped, and
  the step would never pick its geometry again.
- Something skipped on purpose writes a log line that says what and why.
- Never `except: pass`. A caught error goes into the log, even when the run carries on.
- A check that can't be done says so, rather than passing.

**Read the script ahead for key mistakes.** A cheap check here saves time and tokens. A step key mistake stops the run at that step, after Fusion has already done slow
work. [precheck.py](lib/cad_apprentice/precheck.py) finds these by reading the script,
in well under a second, with no Fusion:

- one key written twice in one function, where both calls can run. Calls on two sides of one `if`, in
  different `except` blocks or different `case`s are fine;
- a `uses=` key that no step has: a typo, or a step that was renamed;
- a `chamfer()` after a `fillet()` in one function and component: rule 11 puts the build-plate chamfer
  first. A chamfer that isn't on the build plate says so in a
  `# round-first-ok: <why>` comment on its line;
- an STL exported straight through Fusion. Export with `helpers.write_stl`, which always uses High
  mesh refinement, so no part is printed from a coarse mesh.

Run it with `python3 projects/hobby/cad-apprentice/fusion/lib/cad_apprentice/precheck.py <file or folder>`, and the tests with
`python3 projects/hobby/cad-apprentice/fusion/lib/cad_apprentice/test_precheck.py`. `Builder.step()` also runs it on the first step
from each script file, so a mistake stops the run before any step from that file has run.

- Keys built at run time (`key + '_cut'`, `'hole_%d' % i`, a key passed in a variable) can't be read
  ahead. A `uses=` key that could be one counts as found, and a note says how many such keys there are.
  `step()` still checks every key as it runs.
- Two calls that can't both run for a reason it can't see, like an early `return`, say why in a
  `# twice-ok: <why>` comment on either line.

## Features that survive parameter changes

A feature that works at the default sizes can still warn or break when someone changes one value.
These rules come from fixing that.

19. **Give every plain value a range, and test across it, but not on every run.** Every parameter
    that is a plain value, not a formula, gets `range=` and `step=`: the values it is meant to take.
    - **Guess the range when you make the parameter,** save it in the script and go on with the
      design. Don't stop to ask. When the iteration is ready, list the new ranges with the pictures
      and offer the person a review.
    - **Guess generously, within reason.** A wider range is better unless the design limits it: a
      wall too thin to print, a part bigger than the bed, a count that no longer fits.
    - **When an end fails, use judgement: fix the design or narrow the range.** Designs should be
      robust, so values a person would reasonably pick must work: fix the design for those. Don't
      make the design more complex for edge cases no one will use: narrow the range to what the
      test found works (`RANGE TOO WIDE` gives it). A range the person set themselves is theirs
      to narrow. Decide, act, then show the person what you chose and why with the iteration.
    - **Check the ranges against the design before a full test.** Work out from the design's sizes
      whether each end fits, alone and with every other range at the same end, at both ends of the
      favorites. Narrow what plainly can't fit, so the test doesn't spend trials on it.
    - **When the person asks for the parameter test, run all of it and see it through.** Don't stop
      it after a few trials or test only the parameter you changed, and don't ask whether to go on:
      it catches design problems fast. Act on each failure as above, then show the results.

    The parameter test runs quick stages first and stops at the first stage that fails, so a broken
    end shows up in a few trials: each parameter at both ends, then one step either side of its
    value, then all low and all high at once
    ([lib/README.md § The parameter test](lib/README.md#the-parameter-test)). It treats any warning
    as a failure, not just an error: Fusion keeps a warned feature in the timeline, so it looks fine
    until someone opens it. A full test takes a while, so pick what fits:
    - A new or changed parameter: try just that one, `check:name`, when it lands.
    - The full test: after a batch of changes has piled up, or before calling a design done.
    - Random sets, `check:random=50`: offer them to the person once the full test passes. They try
      every parameter at once, in mixes no stage reaches.

    A line that flipped can stay flipped after the value goes back, and a step bigger than an offset
    in the sketch can flip it ([forum](https://forums.autodesk.com/t5/fusion-design-validate-document/constraints-to-projected-lines-change-when-changing-base-sketch/td-p/11851921)).
    The trials jump on purpose to find that; don't make them smaller. After each put-back the test
    checks every body by name, its volume and box, not just totals, so a part that moved or split
    shows up.
20. **Do only the work the change needs.** Speed matters. If a run didn't touch a part or a sketch,
    don't recapture its pictures or re-export its STL. Rebuild the whole timeline only when an edit
    in place can't do it (rule 27). Say in the status line what was skipped, so the person knows
    what's stale.
21. **The first copy of a patterned cut must hit the part.** Fusion checks the cut on its first copy.
    If that copy misses every body, the feature warns "No target body", even when the other copies
    cut fine. Cut the pattern out of a plain sheet body that is big enough to hold every copy, then
    intersect or subtract the sheet from the part.
22. **Don't join a piece back in.** A New body plus a Join, to put back something a cut took away, can
    lose its profile or leave the piece loose after a size change. Instead, cut that piece out of the
    tool body before the tool cuts the part.
23. **A tool body must stay one body.** If a later cut splits a tool body in two, any combine that
    uses it loses it on the next recompute ("All tool bodies are lost"). Make the tool bigger than
    the part, for example twice as deep, so a strip in front of and behind the part holds it together.
    The extra cuts nothing.
24. **No lists that grow with a parameter.** A combine whose list of bodies depends on a count breaks
    when the count changes. Pattern the feature instead, and combine one fixed body. Fusion won't
    pattern a combine of a copied body: by then the copy is part of the target. So join one copy,
    then pattern the join's faces (`CombineFeature.faces`). The grid grows and shrinks with the
    count, and the part stays one body. The same goes for edges: a
    chamfer on an edge of a pattern's last copy loses that edge when the count drops, and cuts the
    wrong edge, with no warning, when it grows. Pattern to one short, then put the last copy in a
    pattern of 2, so it is always the same copy.
    To trim a part into many pieces, intersect it with one "comb" body: a thin core plus a Join
    tooth at each piece, the tooth patterned. The comb stays one body at any count, so the
    Intersect keeps one tool, and the pieces come out as one body (suspension bridge hangers and
    cable bands). Separate New bodies from one sketch (`every_profile`) are a growing list too: when a
    size change makes two of them touch, Fusion merges them, and a combine that names both loses one
    (suspension bridge corbels at towers 781 mm).
25. **Pick the right body after a split.** A cut that splits a part leaves bodies named "Name (2)".
    Use the biggest one, and report the small ones as loose pieces.
26. **Sketch from what's already there.** Put a sketch's points on projected edges and the axes, and
    size it with the same parameters as the part, so it moves with the part. A point placed only by
    numbers stays behind when a size changes. A sketch that is fully constrained this way can't drift.
    - **Stable references, best first:** origin, axes, the layout sketch, tagged sketch geometry, and
      body edges last.
    - **Project a body edge only when the sketch must follow it.** Pick one made early, never a fillet
      or chamfer edge ([Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/sketching-basics-in-autodesk-fusion/)).
    - **Tie each sketch to the origin or the layout sketch,** not to the sketch before it in a chain. A
      chair built as a chain broke on most single-parameter changes
      ([forum](https://forums.autodesk.com/t5/fusion-design-validate-document/best-practices-for-robust-parametric-designs/td-p/9112280)).
    - **No tangent or coincident constraint on a projected arc.** Fusion treats it as a full circle, so
      a point can jump to the other side. Draw your own fully defined arc in the same place instead:
      same center, radius from the same parameter expression, ends tied to the projected arc's end
      points. Concentric alone is fine, since it ties only the centers, but a shared center isn't enough
      for the replacement arc: a free radius lets points drift. Source: Autodesk bug FUS-125743, with
      the reason and the fix from a forum expert ([forum](https://forums.autodesk.com/t5/fusion-design-validate-document/constraints-to-projected-lines-change-when-changing-base-sketch/td-p/11851921)).
27. **When many steps are renamed, rebuild.** Editing in place with lots of renamed or swapped steps
    can fail with "multiple target" errors. Run the script in clean mode, which wipes the timeline
    and builds it again.
28. **A rename changes names, never values.** After renaming parameters, diff every value against the
    old script. Once, a rename doubled a thickness and the person spotted it, not the agent.
29. **Repeat a feature in 3D, not in the sketch.** For many copies of one shape (lattice bars, holes,
    ribs), draw one copy, cut or extrude it, and pattern that feature, with the count as a
    parameter. Don't put all the copies in one sketch, whether drawn one by one or with a sketch
    pattern. Where copies overlap, the sketch splits into thousands of closed regions. Fusion works
    them all out again on every change, and a cut that takes every region also cuts the gaps between
    the copies. Copies drawn one by one also can't follow a change in the count (rule 24).
30. **Edge features before the cuts that change.** Put the build-plate chamfer and the rounds before
    cuts whose shape follows a parameter (a lattice, a pattern of holes). They then pick plain edges
    that stay the same when the cut changes. One fillet feature per radius, biggest first, inside
    corners before outside: each radius can then be turned off on its own, and the other order often
    fails ([Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/get-smart-with-fusion-360-fillet-best-practices/)).
31. **Limit every count to what the design survives.** For each favorite, find the value where the
    shape stops making sense (a peg left outside its hole, a gap below zero) and set the range
    just inside it. When the test logs `RANGE TOO WIDE`, it has found that edge for you (rule 19).
    The ranges are the Customize sliders' limits. List each favorite's limit in the project README.
32. **Make patterns cheap: the right input, one row, Identical.** In order of what saved the most:
    - **One symmetric pattern, not a row each way.** A second row cuts into what the first already
      cut: two rows of truss holes from the middle took 295 s, one symmetric pattern of 2n − 1 copies
      made the same part in 0.1 s (`circular_pattern(..., symmetric=True)`). Its total angle or length
      covers both sides, so double the one-side value, or the copies crowd in and split the part.
    - **Pattern the feature, not sketch geometry.** Draw one copy, make its feature, pattern the
      feature. A sketch pattern makes the solver carry every copy ([forum](https://forums.autodesk.com/t5/fusion-design-validate-document/understanding-fusion-360-bottlenecks/m-p/6467830), rule 14).
    - **Pattern the cut or join, not bodies a combine then uses** (rule 24). In one forum honeycomb,
      patterning bodies and combining them ran 12 minutes and was stopped; patterning faces of one
      feature took 35 s ([forum](https://forums.autodesk.com/t5/fusion-support-forum/fusion-360-takes-too-long-to-compute-changes/td-p/10382576)).
      Pattern bodies only when the copies stay separate parts. A pattern of bodies has no compute option.
    - **Pick the compute option.** A pattern or mirror of features works out its copies one of three
      ways ([Autodesk blog](https://www.autodesk.com/products/fusion-360/blog/autodesk-fusion-mirror-and-pattern-compute-options/)):
      - **Identical** repeats the first copy's result. Use it when every copy lands on the part the
        same way: holes through one plate, ribs on a flat face if the body count matches Adjust.
      - **Optimized** repeats faces only. Don't use it: on the suspension bridge it gave a different part in 7 of
        11 patterns, with no warning, and it was slower as often as faster. Autodesk says it can fail
        on joins and other contact with faces it didn't copy.
      - **Adjust** works each copy out on its own. The slowest, but almost never wrong. Keep it when
        copies land differently: one runs off an edge, hits a hole, or joins a different body. A
        pattern of a join shows it: in Autodesk's 3×3 example, Optimized made 3 columns. Identical
        made all 9, but only the first joined, and the other 8 came out as separate bodies.

      The API's default is Adjust (the `patternComputeOption` docs in Fusion's `adsk/fusion.py`), so
      every pattern a script makes is the slow kind unless it says otherwise. Pass `compute=` to
      `rect_pattern`, `circular_pattern`, `path_pattern` or `mirror`; a changed option makes the
      feature again.

      On the suspension bridge (2026-11-16) Identical matched Adjust's volume and face count on all
      11 feature patterns, joins included, and cut the slowest from 11.7 s to 0.7 s.

    Read the timings: a pattern that takes more than a few seconds is the first place to look. Try
    Identical and check the volume, face count and body count are the same as under Adjust. Keep it
    only if they are.
33. **On every run, look for slow features and make them cheaper.** The log says "done in N s" for
    each step that took a second or more. After each run, read those lines and name any feature that
    takes far longer than others like it, or longer than its share of the run. Then ask why Fusion
    works hard on it, and whether the design can give it less to do: a smaller sketch (rule 14), a
    3D pattern instead of sketch copies (rule 29), one symmetric row set to Identical (rule 32), one
    fixed body instead of a list (rule 24), a cut into a plain block instead of into a part already
    full of holes. Change the design when the shape stays the same, and say what got faster. If the
    fix would change the shape, propose it with the timings instead (user, 2026-11-16).
    - **A feature in error is slow too.** Fusion retries it on every compute
      ([forum, Autodesk](https://forums.autodesk.com/t5/fusion-support-forum/ridiculously-slow/td-p/9892755)).
    - **Use the fewest features for the shape.** In that thread, 84 features did what 2 would. This
      doesn't override small sketches (rule 14) or one fillet per radius (rule 30).
    - **Split into print pieces near the end of the timeline,** one expert's advice. In his ship
      model, 83 of the 87 slowest features were Splits, though most were deck and bulkhead splits, not
      the print sections ([forum](https://forums.autodesk.com/t5/fusion-support-forum/slow-performance-and-using-components/td-p/9982720)).
    - **While tuning big sizes, lower the counts of small details** (flutes, bands) with their
      parameters, and put them back before the full test. Don't move features in the timeline for
      this: that clashes with rules 11 and 30, and a reorder needs a clean rebuild (rule 27).

## Running a script

**The runner is the default.** After step 1, run
`python3 projects/hobby/cad-apprentice/fusion/tools/fusion_outputs.py run NAME --mode saved` in a background shell. It does steps
2 to 5 with no click on ▶: it preps, has the UpsertTestRunner add-in run the script, prints the log as
it grows, and exits 0 only when the log ends in DONE. The add-in starts with Fusion, so this also works
behind a locked screen. Steps 3 and 4 below are the fallback, for when the add-in doesn't answer. Then
go on with step 6. More on keeping iterations fast: [lib/README.md § Faster iterations](lib/README.md#faster-iterations).

1. For a new design, run
   `python3 projects/hobby/cad-apprentice/fusion/tools/fusion_outputs.py new NAME PROJECT_DIR --doc "Design name"`.
   It writes the entry file, its `.manifest` and a starter `build.py` from [template/](template/), and
   copies the entry file and manifest to a folder of the same name in
   `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/`. The entry file reads the
   real code from the repo, so edits need no new copy.
2. Clear last run's log, pictures and STLs, so you can't read an old result by mistake:
   `python3 projects/hobby/cad-apprentice/fusion/tools/fusion_outputs.py prep NAME --mode saved` (`saved` updates the one saved design, rule 4; `new` only for a first build: run again, it saves a second file under the same name, so `--mode` has no default). It also writes `mode.txt` and
   brings Fusion forward. It's on the allow list, so it runs without asking; don't hand-write `rm`
   lines for this.
3. In the main window, check the tab reads Utilities, since a reopened design starts on Solid, and
   close the Data panel if it is open (its X is at the panel's top right). Click Add-Ins. The icon in
   the same spot on Solid is Revolve, and a wrong click opens Revolve or Move: press their Cancel. If Fusion isn't in front, bring it forward
   first with `open_application "Autodesk Fusion"`; the person often has another app in front. In a
   full-screen Space, see the last fact below. The Data panel on the left moves the Add-Ins icon, so
   take a screenshot before clicking.
4. The Scripts dialog is a separate window in another process, so a background click on it is refused.
   It can open on either monitor, so list the windows if you don't see it. Zoom to check the row, click
   ▶ for that script with a full-screen click, and stop acting. Don't release the screen (rule 5).
   A background click on ▶ reports ok but runs nothing, so the person ends up clicking for
   you. A new tab or a log within a few seconds shows it ran.
5. Show the hidden apps again, only if you hid any. Wait in a background shell loop for the log's
   last line (` DONE`, a traceback, `STOPPED`), without polling. The log grows line by line while it
   runs, so `tail` it to say where a long run is. Read the log and the pictures after.
6. Copy the outputs into the project with `python3 projects/hobby/cad-apprentice/fusion/tools/fusion_outputs.py collect NAME
   projects/<p>`. It lists files this run didn't make (a dropped part's STL and pictures); add
   `--prune` to delete them.

## Gallery pictures

When the person asks for good pictures of a finished model (large views plus close-ups of the details), use
[gallery_shots.py](tools/gallery_shots.py) through the UpsertTestRunner add-in: a request
file with `doc` (the saved design's tab), `out`, and a list of shots, each an eye and target point in mm.
It never changes the design: it inserts it as a linked part into a new tab, takes the pictures there and
closes that tab unsaved. Then [trim_picture.py](tools/trim_picture.py) cuts the white space
off every picture: ratio `0` keeps each picture's own shape, so every picture is cropped tight. Save them in the project's `pictures/gallery/`, without the `view_` prefix, so
`collect` doesn't count them as stale. The suspension bridge demo is the example.

- Use an orthographic camera with `fit` for the whole model. A perspective fit cuts off the near end.
- Use perspective with an eye about 50–150 mm away for close-ups. Edges on for close-ups, off for wide views.
- For one part top to bottom (a tower), shoot a tall picture (`size` [1600, 2400]) and crop it.
- Hiding the origin in the design's own tab marks the tab as changed. That's why the tool works in a new tab.

## Fusion facts that cost time

- The API works in centimetres.
- `unitsManager.evaluateExpression(expr, 'mm')` still answers in cm. Starting geometry drawn 10×
  too small gets pulled to size by the dimensions, and the solver can flip lines to the wrong side.
- `floor` is a function name, so Fusion refuses it as a parameter name. Use `floor_thickness`.
- Python stays running between scripts, so a module you edit is ignored until you drop it from
  `sys.modules` or read the file fresh each run.
- A fillet after a Join can fail, so fillet a body first, then join it.
- `SketchStop` takes effect only after the script yields. Loop on `adsk.doEvents()` with a short sleep,
  then check the sketch is closed.
- A Combine whose tools are pieces of a split body breaks for good once a parameter changes the
  pieces, even after the value is put back. See rules 22 and 23.
- Clear old outputs with `fusion_outputs.py prep` (step 2 above). In a hand-written line, a zsh glob
  with no match stops the whole command.
- A step inside a collapsed timeline group can't be rolled to. Open the groups first.
- `timeline.item(i)` lists a closed group as one item and skips the steps inside it. A probe that
  walks the timeline must call `cad_apprentice.open_groups(tl)` first, or it sees only the
  24 top-level items of a grouped design and finds nothing (suspension bridge, 2026-11-16).
- A symmetric extrude that is given its bodies (a Cut or Join with `participantBodies`) loses "full
  length": Fusion stores it as half on each side, so the feature comes out twice as thick. The library
  sets it back and stops if it won't stick.
- `participantBodies` can't be read on a finished feature unless the timeline is rolled back to it.
- A sketch pattern (`sketch.geometricConstraints.createRectangularPatternInput`) takes a plain Python
  list of sketch entities. An `ObjectCollection` raises a TypeError.
- A save reaches the cloud late, so the version in the log can be one behind the tab.
- Many short lines in one sketch, each tied to two curves and dimensioned, stall the solver: 42
  suspension bridge hangers drawn that way got "over constrained" refusals, then hung Fusion for over 18
  minutes. Draw one wall between the two curves instead and cut it into pieces with a patterned gap
  block (rule 29). A cut that splits a body leaves many bodies, so a later join has to take all of
  them (bridge hangers).
- A distance dimension has no sign. When a parameter drives it to 0, the point can come back on the
  other side when the value grows again. Every step stays healthy, but the shape is different: on the
  suspension bridge a flute row started at the wrong end after towers 781 mm and back. Keep such
  dimensions above 0 across the whole range, for example with `max(1; floor(...))` in a count.
- `addTwoPointRectangle` adds no horizontal or vertical constraints through the API. Add them, or
  the rectangle stays loose.
- While the person is in a full-screen Space, a background click reports ok but does nothing, and
  `open_application` plus a screenshot comes back black. To reach Fusion, run
  `osascript -e 'tell application "System Events" to set frontmost of (first process whose bundle identifier is "com.autodesk.fusion360") to true'`
  and `osascript -e 'tell application id "com.autodesk.fusion360" to activate'`, then take the screenshot
  on the monitor Fusion is on. This pulls them over to Fusion's Space, so tell them.
