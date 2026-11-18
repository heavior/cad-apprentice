# Tools

The command-line tools around a design: start it, check it, run it, collect what it made, and turn
it into pictures and a print project. Run them from the repo root. `K` below stands for
`projects/hobby/cad-apprentice`.

## fusion_outputs.py: start, run and collect a design

`NAME` is the design's script name, the folder in Fusion's Scripts folder (for example
`BuildBikeHolder`).

| Command | What it does |
| --- | --- |
| `python3 K/fusion/tools/fusion_outputs.py new NAME PROJECT_DIR --doc "Design name"` | starts a design from [../template/](../template/): writes the entry file, its manifest and a starter `build.py` to `PROJECT_DIR/scripts/fusion/NAME/`, and copies the entry file and manifest to Fusion's Scripts folder. `--doc` is the name the design is saved under in Fusion. It refuses a name that is already there. |
| `python3 K/fusion/tools/fusion_outputs.py prep NAME --mode MODE` | checks the code, clears last run's log, pictures, STLs and stop file, writes `mode.txt`, and brings Fusion to the front. For a run by hand with ▶. |
| `python3 K/fusion/tools/fusion_outputs.py run NAME --mode MODE` | does `prep`, then has the runner add-in run the script with no click. Prints the log as it grows. Exits 0 only when the log ends in `DONE` and no check after it failed. Run it in a background shell. |
| `python3 K/fusion/tools/fusion_outputs.py collect NAME PROJECT_DIR` | copies the STLs to `PROJECT_DIR/stl/`, `view_*.png` to `pictures/` and `sketch_*.png` to `pictures/sketches/`, then lists the files there that this run didn't make. `--prune` deletes those from disk. It stages nothing; a file git tracks comes back with `git checkout`. |

Options:

- `--mode` has no default, so a run never saves a second design by accident:
  - `new` builds in a new tab and saves it as a new design. Only for the first build.
  - `saved` updates the saved design and saves a new version. The normal round.
  - `clean` wipes the saved design's timeline and builds it all again. For big changes.
  - `check` is `saved`, plus a rerun that should change nothing, plus the parameter test.
  - `night` builds in a new tab and does the same checks, but never saves. Save the tab by hand if
    you like it.
  - `check:width,height` (or `night:...`) runs the parameter test on those parameters only.
  - `probe:FILE` runs a throwaway test script once, in place of the design. The entry file then sets
    `mode.txt` back to `saved`.
  - No `mode.txt` at all (a run with ▶ after a crash) means `saved`. On a first build that stops with
    "no saved design", and `new` stops if a design with that name is already saved.
- `--no-check` skips the code checks, for a one-off rerun of an older script that fails them.
- `--wait MINUTES` (`run` only): give up after this many minutes with no new log line. Default 30.

How `run` behaves:

- **One run per design at a time.** A second `run` of the same design stops at once, since its `prep`
  would delete the first one's log and pictures. The lock (`run.lock` in the design's Scripts
  folder) is left by a killed run only; the next run clears it.
- **Stopped before Fusion starts it,** `run` takes its request back and prints "request withdrawn,
  nothing ran". Once Fusion has started, the run finishes there.
- **A request has an expiry,** the `--wait` time. The runner refuses one older than that, so a
  request left behind never starts hours later.
- **Exit 1 with `CHECK FAILED`** when the build reached `DONE` but a check after it logged `TRIAL
  FAILED`, `RANGE TOO WIDE`, `RERUN CHANGED SOMETHING` or `LOOSE PIECES`. The lines are printed.
- **A crash during a run:** `run` requests aren't run again after a crash. Other requests are,
  at most twice. A request file that isn't JSON goes to `K/fusion/tests/run/bad/`.

## Checks

Both are plain Python and need no Fusion. `prep` and `run` call them on the design's code and the
library.

- **[precheck.py](../lib/cad_apprentice/precheck.py)** reads a build script and finds step-key
  mistakes that would stop a run halfway: a key written twice, a fixed key inside a loop, a key in `uses=` that no step has, a
  chamfer after a round. It also stops an STL export that skips the library's `write_stl`, so every
  STL is made at High mesh refinement. `python3 K/fusion/lib/cad_apprentice/precheck.py <file or folder>`
- **[check_slow.py](../lib/cad_apprentice/check_slow.py)** finds Fusion calls that can take long
  with no `slow()` around them. `python3 K/fusion/lib/cad_apprentice/check_slow.py <file or folder>`.
  It also runs as a hook after every file the agent writes. A call that is fine without one says why
  in a `# slow-ok: <why>` comment.

## Runner scripts

These run inside Fusion, through the runner add-in ([../runner/](../runner/)). Each run is a request
file the agent drops into `K/fusion/tests/run/requests/<id>.json`: `{"id": ..., "file": ...,
"args": {...}}`. `file` is relative to `K/fusion/`. The add-in calls the file's `main(args)` and writes
the result to `K/fusion/tests/run/results/<id>.json`. Write the request as `.tmp` first, then rename
it, so the add-in never reads half a file.

- **[run_design.py](run_design.py)** runs a design's entry file, the same file ▶ runs. `args`:
  `{"name": NAME}`. `fusion_outputs.py run` uses it; you rarely call it yourself.
- **[gallery_shots.py](gallery_shots.py)** takes gallery pictures of a saved design without changing
  it: it inserts the design as a linked part into a new tab, takes the pictures there, and closes that
  tab unsaved. `args`: `doc` (the saved design's tab name), `out` (folder), `size` `[w, h]`, and
  `shots`, each `{name, eye, target}` in mm, with `fov` or `extent`, `edges`, `fit` and `size` as
  options. More in [../rules.md § Gallery pictures](../rules.md#gallery-pictures).

## Picture tool

- **[trim_picture.py](trim_picture.py)** cuts the white space around a picture down to the model
  plus a margin. `python3 K/fusion/tools/trim_picture.py in.png out.png [ratio] [pad]`. Ratio `0`
  keeps the model's own shape; a width:height ratio pads with white to that shape.

## 3MF tools

For the Bambu Studio print project. They need Bambu Studio installed. How to use them in a design
round: [../../3dprinting/rules.md](../../3dprinting/rules.md).

- **[build_3mf.py](../../3dprinting/build_3mf.py)** makes a new `.3mf` from STLs, one plate per part,
  with the settings of a template project. It won't overwrite a `.3mf` that exists.
  `python3 K/3dprinting/build_3mf.py OUT.3mf --approved "<the person's OK>" [--settings-from REF.3mf] [--down PART=-y] a.stl b.stl ...`
  `--settings-from` takes the settings from another project instead of the template.
- **[update_3mf.py](../../3dprinting/update_3mf.py)** swaps new STLs into an existing `.3mf` and
  keeps everything the person set up in it: settings, turns, copies, plates.
  `python3 K/3dprinting/update_3mf.py PROJECT.3mf --approved "<the person's OK>" [--down PART=-y] a.stl b.stl ...`
  `--down` turns only a new part; a part already in the project keeps its turn.
- **[make_template.py](../../3dprinting/make_template.py)** makes the empty template project from a
  tuned one: global settings only, one empty plate, no parts.
  `python3 K/3dprinting/make_template.py FROM.3mf [OUT.3mf] [--filament N=OTHER.3mf:M]`
  `--filament` puts filament M of `OTHER.3mf` into slot N, when `FROM` has the wrong filament there.
