"""Run every 3MF test in the plan's order and write the results (3dprinting/3mf-test-scenarios.md § 4).

Order: B, then the U group alone. Every .3mf under projects/ (but not the tests'
own run/ folder) is read at the start and at the end of the run; one that changed in between is
listed and fails the run.

Usage: python3 3dprinting/tests/run_tests.py
Writes run/results/results.json, run/results/results.txt, run/results/sha1-start.txt and sha1-after.txt.
"""
import json, os, re, sys, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa
import common

# Worse wins when one test has several results (its subtests, or a check skipped inside a pass).
RANK = {'pass': 0, 'skip': 1, 'fail': 2, 'error': 3}


def first_line(err):
    text = str(err[1]).strip()
    return text.splitlines()[0][:300] if text else err[0].__name__


def tests_in(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from tests_in(t)
        else:
            yield t


class Recorder(unittest.TextTestResult):
    """Keeps one row per test: pass, fail, error or skip, and one line why. A subtest counts towards
    its test. A skip or error of a whole class (setUpClass) is kept apart and given to its tests."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.by_test = {}
        self.holders = []

    def row(self, test, status, why):
        if isinstance(test, unittest.case._SubTest):
            why = '%s: %s' % (test._subDescription().strip(), why) if why else why
            test = test.test_case
        if not isinstance(test, unittest.TestCase):  # setUpClass / setUpModule: no test of its own
            self.holders.append((test.id(), status, why))
            return
        name = test.id().split('.')[-1]
        old = self.by_test.get(test.id())
        if old and RANK[old['status']] >= RANK[status]:
            return
        m = re.match(r'test_([BUP]\d+)', name)
        self.by_test[test.id()] = {'id': m.group(1) if m else name, 'test': name, 'status': status,
                                   'why': why, 'note': common.NOTES.get(name, '')}

    def addSuccess(self, test):
        super().addSuccess(test)
        skipped = getattr(test, 'skipped_parts', None)
        self.row(test, 'skip' if skipped else 'pass', 'passed, but skipped: ' + '; '.join(skipped) if skipped else '')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.row(test, 'fail', first_line(err))

    def addError(self, test, err):
        super().addError(test, err)
        self.row(test, 'error', '%s: %s' % (err[0].__name__, first_line(err)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.row(test, 'skip', reason)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is None:
            self.row(test, 'pass', '')
        elif issubclass(err[0], test.failureException):
            self.row(subtest, 'fail', first_line(err))
        else:
            self.row(subtest, 'error', '%s: %s' % (err[0].__name__, first_line(err)))

    def rows_for(self, ids, count):
        """One row per test id, in order. A test with no result gets its class's skip or error, or
        an error row: a test must never drop out of the summary."""
        rows, extra = [], []
        for tid in ids:
            r = self.by_test.get(tid)
            if r is None:
                name = tid.split('.')[-1]
                m = re.match(r'test_([BUP]\d+)', name)
                holder = [h for h in self.holders if re.search(r'\((\S+)\)', h[0]) and tid.startswith(re.search(r'\((\S+)\)', h[0]).group(1) + '.')]
                status, why = (holder[0][1], holder[0][2]) if holder else ('error', 'no result recorded')
                r = {'id': m.group(1) if m else name, 'test': name, 'status': status, 'why': why}
            r['note'] = common.NOTES.get(r['test'], '')
            rows.append(r)
        # A class error after its tests ran (tearDownClass) has no row of its own: listed apart.
        for hid, status, why in self.holders:
            if status == 'error':
                extra.append('%s: %s' % (hid, why))
        assert len(rows) == count, '%d rows for %d tests' % (len(rows), count)
        return rows, extra


def snapshot(label):
    """sha1 of every .3mf under projects/, written to run/results/sha1-<label>.txt."""
    now = project_3mfs()
    with open(os.path.join(RESULTS, 'sha1-%s.txt' % label), 'w') as f:
        f.write(''.join('%s  %s\n' % (h, p) for p, h in sorted(now.items())))
    return now


def load(modules):
    return unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in modules)


def run(modules, stream, out):
    suite = load(modules)
    # The runner empties the suite as it goes, so the ids and the count are taken first.
    ids, count = [t.id() for t in tests_in(suite)], suite.countTestCases()
    r = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Recorder).run(suite)
    try:
        rows, extra = r.rows_for(ids, count)
    except AssertionError as e:
        rows, extra = [], ['%s: %s' % (', '.join(modules), e)]
    out['class_errors'] += extra
    return rows


def skip_rows(modules, why):
    """A skip row for each test of these modules, when they can't run at all."""
    rows = []
    for t in tests_in(load(modules)):
        name = t.id().split('.')[-1]
        m = re.match(r'test_([BUP]\d+)', name)
        rows.append({'id': m.group(1) if m else name, 'test': name, 'status': 'skip', 'why': why, 'note': ''})
    return rows


def main():
    start = time.strftime('%Y-%m-%d %H:%M:%S')
    log = open(os.path.join(RESULTS, 'run.log'), 'w')
    before = snapshot('start')
    out = {'start': start, 'bambu_before': bambu_running(), 'rows': [], 'class_errors': []}
    if out['bambu_before']:
        log.write('Bambu Studio is running: %s\n' % out['bambu_before'])
    out['rows'] += run(['test_build_3mf'], log, out)
    # U only with no Bambu Studio running: update_3mf.py refuses then (§ 1).
    busy = bambu_running()
    if busy:
        out['u_skipped'] = 'Bambu Studio is running: %s' % busy
        out['rows'] += skip_rows(['test_update_3mf'], 'Bambu Studio is open')
    else:
        out['rows'] += run(['test_update_3mf'], log, out)
    after = snapshot('after')
    out['projects_changed'] = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    out['end'] = time.strftime('%Y-%m-%d %H:%M:%S')
    key = lambda r: ('BPU'.index(r['id'][0]) if r['id'][0] in 'BPU' else 3, int(re.sub(r'\D', '', r['id']) or 0))
    out['rows'].sort(key=key)
    with open(os.path.join(RESULTS, 'results.json'), 'w') as f:
        json.dump(out, f, indent=1)
    counts = {s: sum(1 for r in out['rows'] if r['status'] == s) for s in ('pass', 'fail', 'error', 'skip')}
    lines = ['3MF tests, %s to %s' % (start, out['end']),
             'pass %(pass)d, fail %(fail)d, error %(error)d, skip %(skip)d' % counts,
             '.3mf under projects/ changed during the run: %s' % (', '.join(out['projects_changed']) or 'none'), '']
    lines += ['class error: ' + e for e in out['class_errors']]
    for r in out['rows']:
        lines.append('%-4s %-5s %s' % (r['id'], r['status'], r['why'] or r['note']))
    with open(os.path.join(RESULTS, 'results.txt'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return 1 if counts['fail'] or counts['error'] or out['class_errors'] or out['projects_changed'] else 0


if __name__ == '__main__':
    sys.exit(main())
