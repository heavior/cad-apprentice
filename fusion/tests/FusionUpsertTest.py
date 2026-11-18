# Fusion runs this file from its Scripts folder. Link it there (ln -s, not a copy) so KIT finds the
# kit's fusion/ folder; with a plain copy, set KIT by hand. The real code is read from the kit, so
# there's nothing else to copy. The log goes next to this file.
import os, sys, traceback
HERE = os.path.dirname(os.path.realpath(__file__))
KIT = os.path.dirname(HERE)  # tests -> fusion
LIB = os.path.join(KIT, 'lib')
def run(context):
    try:
        if LIB not in sys.path:
            sys.path.insert(0, LIB)
        # Fusion keeps Python running between scripts, so drop the last run's copy.
        sys.modules.pop('cad_apprentice', None)
        path = os.path.join(KIT, 'tests', 'test_components.py')
        scope = {'__name__': 'upsert_test', '__file__': path, 'OUT_DIR': HERE}
        exec(compile(open(path).read(), path, 'exec'), scope)
        scope['run'](context)
    except:
        open(os.path.join(HERE, 'FusionUpsertTest.log'), 'w').write(traceback.format_exc())
