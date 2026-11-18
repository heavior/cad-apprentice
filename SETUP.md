# Setup

This was built on a Mac with Fusion's own Python. `<kit>` below is the kit's folder: the plugin's
folder if your agent installed it as a plugin, or your own copy.

Fusion can't see where your agent keeps the kit, and a plugin's folder moves with each update. So
the kit keeps one small file where Fusion can find it,
`~/Library/Application Support/cad-apprentice/kit.txt`, with the kit's folder in it. Fusion's
runner add-in and each design's entry file read it.

1. **Point Fusion at the kit:** `python3 <kit>/fusion/tools/fusion_outputs.py setup`. It writes
   `kit.txt` and copies the runner add-in (step 4) into Fusion's AddIns folder. Then restart Fusion.
   `setup --check` says whether Fusion uses this kit, and changes nothing. After the kit is updated
   or moved, run `setup` again and restart Fusion.
2. **The library** is [fusion/lib/cad_apprentice/](fusion/lib/cad_apprentice/). A design's entry file adds `fusion/lib`
   to `sys.path` and drops `cad_apprentice` from `sys.modules` before each run. Fusion keeps Python
   running between scripts, so without that an edit here is ignored until Fusion restarts.
3. **A design's entry file** lives in Fusion's Scripts folder
   (`~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/<Name>/<Name>.py`). It
   is a few lines: it reads `mode.txt` next to it, and runs the real script from your project.
   `python3 <kit>/fusion/tools/fusion_outputs.py new NAME PROJECT_DIR --doc "Design name"`
   makes one from [fusion/template/](fusion/template/), with a starter `build.py` in the project,
   and copies it into the Scripts folder.
4. **The runner add-in,** `CadApprenticeRunner` (recommended). On its own, Fusion runs a script only
   when someone clicks ▶ in its Scripts dialog. So without the add-in, the agent has to take over
   your mouse for every run, or wait for you to click. The add-in starts with Fusion and watches a
   folder, `~/Library/Application Support/cad-apprentice/run/requests/`: the agent drops a small
   request file there, and the add-in runs that script. You keep your mouse and screen, and runs
   still work while the computer is locked. It loads [runner.py](fusion/runner/runner.py) from the
   kit folder in `kit.txt`.
5. **Run a design:** `python3 <kit>/fusion/tools/fusion_outputs.py run NAME --mode saved` (or `clean`,
   `new`, `check`). It checks the script, drops a request for the add-in, and prints the log as it
   grows. Without the add-in, run the entry file with ▶ in Fusion's Scripts dialog.
