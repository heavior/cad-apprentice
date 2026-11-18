# Runs scenarios from upsert-test-scenarios.md through the CadApprenticeRunner add-in. A request names them:
# {"id": "bugs", "file": "tests/upsert_suite.py", "args": {"ids": ["E3", "E4"]}}
# Each scenario's result goes to run/results/<request id>/<scenario>.json, with its run logs in a folder
# of the same name. A request cut off by a crash runs again with resume set: finished scenarios are
# skipped, and the one it was in counts as crashed (skipped after two crashes).
import json, os, time, traceback
import adsk.core, adsk.fusion
import upsert_harness as H
import upsert_model as M
import upsert_scenarios as SC

app = adsk.core.Application.get()


def note(line):
    with open(os.path.join(OUT_DIR, 'progress.log'), 'a') as f:
        f.write('%s %s\n' % (time.strftime('%H:%M:%S'), line))


SC.note = note


def main(args):
    ids = args.get('ids') or list(SC.ORDER)
    done = {}
    crashes = {}
    state_path = os.path.join(OUT_DIR, 'state.json')
    if args.get('resume') and os.path.exists(state_path):
        crashes = json.load(open(state_path)).get('crashes', {})
    summary = []
    for sid in ids:
        path = os.path.join(OUT_DIR, sid + '.json')
        if os.path.exists(path):
            summary.append(json.load(open(path)))
            continue
        state = json.load(open(state_path)) if os.path.exists(state_path) else {}
        if state.get('current') == sid:
            crashes[sid] = crashes.get(sid, 0) + 1
        if crashes.get(sid, 0) >= 2:
            res = {'id': sid, 'status': 'skipped', 'error': 'crashed Fusion twice'}
            json.dump(res, open(path, 'w'), indent=1, default=str)
            summary.append(res)
            continue
        json.dump({'current': sid, 'crashes': crashes}, open(state_path, 'w'))
        note('start %s' % sid)
        res = run_one(sid)
        json.dump(res, open(path, 'w'), indent=1, default=str)
        note('end %s: %s' % (sid, res['status']))
        summary.append(res)
        json.dump({'current': None, 'crashes': crashes}, open(state_path, 'w'))
    scenarios = [{'id': r['id'], 'status': r['status'], 'fails': r.get('fails', [])[:6], 'flags': r.get('flags', []),
                  'error': (r.get('error') or '')[-600:]} for r in summary]
    counts = {}
    for r in summary:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    return {'status': 'pass' if counts.get('pass', 0) == len(summary) else 'fail', 'counts': counts,
            'flag_count': sum(len(r['flags']) for r in scenarios), 'scenarios': scenarios}


def open_tabs():
    # Every open tab and whether it has unsaved changes (§ 2 check 7).
    return sorted((d.name, d.isModified) for d in app.documents)


def run_one(sid):
    fn = SC.SCENARIOS.get(sid)
    if fn is None:
        return {'id': sid, 'status': 'missing', 'error': 'no such scenario'}
    t0 = time.time()
    S = H.Scenario(sid, OUT_DIR, M.describe, note)
    tabs = open_tabs()
    try:
        out = fn(S)
        res = S.result()
        if isinstance(out, dict):
            res.update(out)
    except H.Failed as err:
        res = S.result()
        res['status'] = 'fail'
        res['fails'].insert(0, str(err))
    except Exception:
        res = S.result(error=traceback.format_exc())
    finally:
        S.close()
    if open_tabs() != tabs and res['status'] in ('pass', 'fail'):
        res['status'] = 'fail'
        res['fails'].append('7 nothing else touched: tabs %s | %s' % (tabs, open_tabs()))
    res['seconds'] = round(time.time() - t0, 1)
    return res
