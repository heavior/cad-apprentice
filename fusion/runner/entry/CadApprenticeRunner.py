# The file Fusion runs from its AddIns folder. `fusion_outputs.py setup` copies this folder to
# ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/CadApprenticeRunner.
# The real code is read from the kit folder named in kit.txt, which setup writes. An agent's plugin
# folder moves with each update, so after an update, setup writes the new folder there; this copy
# stays as it is.
import os, time, traceback
DATA = os.path.expanduser('~/Library/Application Support/cad-apprentice')
LOG = os.path.join(DATA, 'run', 'runner.log')
scope = {'__name__': 'cad_apprentice_runner'}


def run(context):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        kit = open(os.path.join(DATA, 'kit.txt'), encoding='utf-8').read().strip()
        code = os.path.join(kit, 'fusion', 'runner', 'runner.py')
        scope['__file__'] = code
        exec(compile(open(code, encoding='utf-8').read(), code, 'exec'), scope)
        scope['start'](context)
    except:
        with open(LOG, 'a') as f:
            f.write('%s entry failed:\n%s\n' % (time.strftime('%H:%M:%S'), traceback.format_exc()))


def stop(context):
    if 'stop' in scope:
        scope['stop'](context)
