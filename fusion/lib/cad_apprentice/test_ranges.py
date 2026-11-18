# Tests for ranges.py. Plain Python, no Fusion needed:
#   python3 fusion/lib/cad_apprentice/test_ranges.py
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ranges

fails = []


def expect(ok, what):
    print('%s  %s' % ('ok  ' if ok else 'FAIL', what))
    if not ok:
        fails.append(what)


def refused(what, *args):
    try:
        ranges.check(*args)
    except Exception as err:
        expect(True, '%s: %s' % (what, err))
        return
    expect(False, '%s was not refused' % what)


expect(ranges.check('w', '40 mm', 'mm', '20 mm', '80 mm', '5 mm') == (20, 80, 5), 'R1 a range in mm')
expect(ranges.check('w', '40 mm', 'mm', 20, 80, 5) == (20, 80, 5), 'R2 bare numbers take the unit')
expect(ranges.check('n', '4', '', 2, 8, None) == (2, 8, 1), 'R3 a count steps by 1')
expect(ranges.check('t', '0.4 mm', 'mm', '0.2 mm', '1 mm', '0.05 mm') == (0.2, 1, 0.05), 'R4 a fine step')
refused('R5 a formula', 'p', 'base_w / 4', 'mm', 5, 20, 1)
refused('R6 low above high', 'w', '40 mm', 'mm', 80, 20, 5)
refused('R7 a step that does not fit', 'w', '40 mm', 'mm', 20, 82, 5)
refused('R8 a value outside the range', 'w', '90 mm', 'mm', 20, 80, 5)
refused('R9 a value between steps', 'w', '42 mm', 'mm', 20, 80, 5)
refused('R10 another unit', 'w', '40 mm', 'mm', '2 cm', '8 cm', '5 mm')
refused('R11 no step for a length', 'w', '40 mm', 'mm', 20, 80, None)
refused('R12 a step of 0', 'n', '4', '', 2, 8, 0)

expect(ranges.load(ranges.store(0.2, 1.0, 0.05)) == (0.2, 1.0, 0.05), 'R13 store and load round-trip')
expect(ranges.text(0.15000000000000002, 'mm') == '0.15 mm' and ranges.text(3, '') == '3', 'R14 values print clean')
expect([ranges.text(x, 'mm') for x in ranges.grid(0.2, 0.4, 0.05)] == ['0.2 mm', '0.25 mm', '0.3 mm', '0.35 mm', '0.4 mm'], 'R15 grid without float drift')

print('%d failed' % len(fails))
sys.exit(1 if fails else 0)
