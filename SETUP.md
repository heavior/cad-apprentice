# Setup

This was built on a Mac with Fusion's own Python. The code finds its own folders, so the skill can
sit anywhere. Only the small files copied into Fusion's folders hold a full path; change it there
if your copy lives somewhere else.

1. **The library** is [fusion/lib/cad_apprentice/](fusion/lib/cad_apprentice/). A design's entry file adds `fusion/lib`
   to `sys.path` and drops `cad_apprentice` from `sys.modules` before each run. Fusion keeps Python
   running between scripts, so without that an edit here is ignored until Fusion restarts.
2. **A design's entry file** lives in Fusion's Scripts folder
   (`~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/<Name>/<Name>.py`). It
   is a few lines: it reads `mode.txt` next to it, and runs the real script from the repo.
   `python3 ~/cad-apprentice/fusion/tools/fusion_outputs.py new NAME PROJECT_DIR --doc "Design name"`
   makes one from [fusion/template/](fusion/template/), with a starter `build.py` in the project,
   and copies it into the Scripts folder.
3. **The runner add-in** (optional, recommended). On its own, Fusion runs a script only when
   someone clicks ▶ in its Scripts dialog. So without the add-in, the agent has to take over your
   mouse for every run, or wait for you to click. The add-in starts with Fusion and watches a
   folder: the agent drops a small request file there, and the add-in runs that script. You keep
   your mouse and screen, and runs still work while the computer is locked. Link
   [fusion/runner/entry/](fusion/runner/entry/) into Fusion's AddIns folder (a link, not a copy, so
   it finds the skill):
   `ln -s ~/cad-apprentice/fusion/runner/entry ~/Library/Application\ Support/Autodesk/Autodesk\ Fusion\ 360/API/AddIns/UpsertTestRunner`
   Then restart Fusion. It starts with Fusion, loads [runner.py](fusion/runner/runner.py) from the skill's folder
   and watches `fusion/tests/run/requests/`.
4. **Run a design:** `python3 ~/cad-apprentice/fusion/tools/fusion_outputs.py run NAME --mode saved` (or `clean`,
   `new`, `check`). It checks the script, drops a request for the add-in, and prints the log as it
   grows. Without the add-in, run the entry file with ▶ in Fusion's Scripts dialog.
