# The file Fusion runs from its AddIns folder. The real code is read from the kit. Link this folder
# (ln -s, not a copy) to
# ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/UpsertTestRunner
# so the paths below find the kit. With a plain copy, set FUSION to the kit's fusion/ folder by hand.
import os, time, traceback
FUSION = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))  # entry -> runner -> fusion
CODE = os.path.join(FUSION, 'runner', 'runner.py')
LOG = os.path.join(FUSION, 'tests', 'run', 'runner.log')
scope = {'__name__': 'upsert_test_runner', '__file__': CODE}


def run(context):
    try:
        exec(compile(open(CODE, encoding='utf-8').read(), CODE, 'exec'), scope)
        scope['start'](context)
    except:
        with open(LOG, 'a') as f:
            f.write('%s entry failed:\n%s\n' % (time.strftime('%H:%M:%S'), traceback.format_exc()))


def stop(context):
    if 'stop' in scope:
        scope['stop'](context)
