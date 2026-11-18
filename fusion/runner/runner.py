# Runs test requests in Fusion with nobody at the screen. The add-in entry in Fusion's AddIns folder
# reads this file from the repo and calls start(). A background thread watches the requests folder and
# fires a custom event; Fusion runs the handler on its main thread, where API calls are safe. The
# handler reads handle.py from the repo on every request, so a fix there needs no restart. A change
# to this file does. Plan: ../tests/upsert-test-scenarios.md § 1.
import json, os, threading, time, traceback
import adsk.core

# The kit's folder is found from this file, so the kit can live anywhere.
KIT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
RUN = os.path.join(KIT, 'tests', 'run')
REQUESTS = os.path.join(RUN, 'requests')
EVENT = 'FusionKitRunnerRequest'

app = adsk.core.Application.get()
kept = []  # Fusion drops handlers nobody holds on to.
state = {'busy': False, 'fired': 0}
quit_flag = threading.Event()
logged = set()


def note_once(what):
    # An error that repeats every 2 seconds is logged once, not 1,800 times an hour.
    err = traceback.format_exc()
    if err not in logged:
        logged.add(err)
        note('%s failed:\n%s' % (what, err))


def note(line):
    with open(os.path.join(RUN, 'runner.log'), 'a') as f:
        f.write('%s %s\n' % (time.strftime('%H:%M:%S'), line))


class Handler(adsk.core.CustomEventHandler):
    def notify(self, args):
        # Startup can bring up a sign-in or recovery screen; nothing runs until Fusion says it's up. It's
        # read here, on the main thread, not in the watcher, which fires again a minute later.
        if not app.isStartupComplete:
            return
        state['fired'] = 0
        # Fusion can deliver the next event inside adsk.doEvents(), which the tests call, so one run
        # could start inside another.
        if state['busy']:
            return
        state['busy'] = True
        try:
            path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'handle.py')
            scope = {'__name__': 'upsert_test_handle', '__file__': path, 'RUN': RUN, 'note': note}
            exec(compile(open(path, encoding='utf-8').read(), path, 'exec'), scope)
            scope['handle'](app)
        except:
            note('handler failed:\n' + traceback.format_exc())
        finally:
            state['busy'] = False


# A request in active/ while nothing runs was cut off by a crash; the handler picks it up again.
def ready():
    try:
        waiting = [n for d in (REQUESTS, os.path.join(RUN, 'active')) if os.path.isdir(d) for n in os.listdir(d) if n.endswith('.json')]
        return bool(waiting)
    except:
        note_once('looking for requests')
        return False


def watch():
    while not quit_flag.wait(2):
        # An event that never arrives (a modal dialog) is fired again after a minute.
        # One error must not end the thread: the add-in would look loaded and do nothing.
        try:
            if not state['busy'] and time.time() - state['fired'] > 60 and ready():
                state['fired'] = time.time()
                app.fireCustomEvent(EVENT, '')
        except:
            note_once('the watch loop')


def start(context):
    os.makedirs(REQUESTS, exist_ok=True)
    ev = app.registerCustomEvent(EVENT)
    h = Handler()
    ev.add(h)
    kept.extend([ev, h])
    threading.Thread(target=watch, daemon=True).start()
    note('runner started, pid %d' % os.getpid())


def stop(context):
    quit_flag.set()
    try:
        app.unregisterCustomEvent(EVENT)
    except:
        note_once('unregistering the event')
    note('runner stopped')
