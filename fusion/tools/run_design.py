# Runs a design's build script through the UpsertTestRunner add-in, so nobody has to click ▶ in the
# Scripts dialog (once, a run sat 62 minutes behind a locked screen waiting for that click).
# `fusion_outputs.py run NAME` drops the request; the add-in calls main() on Fusion's main thread.
# It runs the design's own entry file from Fusion's Scripts folder, the same file ▶ runs, so the
# mode.txt, the log and the pictures are where they always are.
import os, sys

SCRIPTS = os.path.expanduser('~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts')


def main(args):
    name = args['name']
    path = os.path.join(SCRIPTS, name, name + '.py')
    # The entry file drops cad_apprentice itself. Its helpers go too, or a fix there would wait for a restart.
    for m in [m for m in sys.modules if m == 'cad_apprentice' or m.startswith('cad_apprentice.')]:
        del sys.modules[m]
    scope = {'__name__': 'design_' + name, '__file__': path}
    exec(compile(open(path, encoding='utf-8').read(), path, 'exec'), scope)
    scope['run']({})
    log = os.path.join(SCRIPTS, name, name + '.log')
    lines = open(log, encoding='utf-8').read().splitlines() if os.path.exists(log) else []
    return {'done': any(l.endswith(' DONE') or l == 'DONE' for l in lines[-5:]), 'last': lines[-15:]}
