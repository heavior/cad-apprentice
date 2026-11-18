# Fusion runs this copy from its Scripts folder. The real code is read from the repo, so
# there's nothing else to copy. Logs and renders go next to this file. A mode.txt beside it
# picks the run (build_bridge.py lists the modes); fusion_outputs.py writes it.
import os, sys, traceback
HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.expanduser('~/cad-apprentice')
CODE = os.path.join(REPO, 'demos/suspension-bridge/scripts/fusion/BuildSuspensionBridge')
LIB = os.path.join(REPO, 'fusion/lib')
def run(context):
    try:
        mode_file = os.path.join(HERE, 'mode.txt')
        # No mode.txt means saved: on a first build that stops with "no saved design", where new would
        # save a second copy of a design that exists.
        mode = open(mode_file).read().strip() if os.path.exists(mode_file) else 'saved'
        if LIB not in sys.path:
            sys.path.insert(0, LIB)
        # Fusion keeps Python running between scripts, so drop the last run's copy.
        # cad_apprentice.helpers and the other submodules too, or an edited helper isn't picked up.
        for m in [m for m in sys.modules if m == 'cad_apprentice' or m.startswith('cad_apprentice.')]:
            del sys.modules[m]
        path = os.path.join(CODE, 'build_bridge.py')
        # 'probe:<file>' runs a throwaway test script instead, once: mode.txt goes back to saved first,
        # so ▶ later runs the design, not a leftover probe.
        if mode.startswith('probe:'):
            path = mode[len('probe:'):]
            open(mode_file, 'w').write('saved\n')
        scope = {'__name__': 'suspension_bridge', '__file__': path, 'OUT_DIR': HERE, 'MODE': mode, 'CODE': CODE}
        exec(compile(open(path, encoding='utf-8').read(), path, 'exec'), scope)
        scope['run'](context)
    except:
        # Added at the end, so the lines showing how far the build got stay.
        open(os.path.join(HERE, 'BuildSuspensionBridge.log'), 'a').write(traceback.format_exc())
