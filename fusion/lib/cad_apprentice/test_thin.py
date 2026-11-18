# Tests for thin.py. Plain Python, no Fusion needed:
#   python3 lib/cad_apprentice/test_thin.py
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thin

fails = []


def expect(ok, what):
    print('%s  %s' % ('ok  ' if ok else 'FAIL', what))
    if not ok:
        fails.append(what)


class FakeParam:
    def __init__(self, cm):
        self.value = cm


class FakeDesign:
    def __init__(self, mm):
        self.userParameters = self
        self.mm = mm

    def itemByName(self, n):
        return FakeParam(self.mm[n] / 10) if n in self.mm else None


expect(thin.below([('a', 0.5), ('b', 0.2), ('c', 0.3)]) == [('b', 0.2), ('c', 0.3)], 'T1 parts under 0.4 mm, thinnest first')
expect(thin.below([('a', 0.4), ('b', 0.4000000001)]) == [], 'T2 exactly the floor is not thin')
expect(thin.below([('a', 0.8)], floor=1) == [('a', 0.8)], 'T3 another floor')
expect(thin.text([('flute', 0.123)]) == 'flute 0.12 mm', 'T4 text')

log = []
w = thin.Watch(['flute', 'slab'], log)
w(FakeDesign({'flute': 1.3, 'slab': 1.0}), 'build')
expect(log == [], 'T5 nothing logged when nothing is thin')
got = w(FakeDesign({'flute': 0.2, 'slab': 0.3}), 'trial 4')
expect(got == [('flute', 0.2), ('slab', 0.3)] and log[-1] == 'THIN (under 0.4 mm) trial 4: flute 0.20 mm, slab 0.30 mm', 'T6 a thin trial is logged, not raised')
w(FakeDesign({'flute': 0.35, 'slab': 1.0}), 'trial 5')
expect(w.summary() == 'thin parts: 2 of 3 checks had parts under 0.4 mm; thinnest flute 0.20 mm (trial 4)', 'T7 summary keeps the thinnest')
expect(thin.Watch([], []).summary() == 'thin parts: none under 0.4 mm in 0 checks', 'T8 summary with nothing thin')
try:
    w(FakeDesign({'flute': 1}), 'build')
    expect(False, 'T9 a missing parameter was not refused')
except Exception as err:
    expect('no parameter slab' in str(err), 'T9 a missing parameter is refused: %s' % err)

print('%d failed' % len(fails))
sys.exit(1 if fails else 0)
