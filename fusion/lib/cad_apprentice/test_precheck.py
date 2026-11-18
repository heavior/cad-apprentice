# Tests for precheck.py. Plain Python, no Fusion needed:
#   python3 fusion/lib/cad_apprentice/test_precheck.py
# Each case is a small script (line 1 is its first line); the test says which lines must be flagged
# and checks nothing else is.
import os, re, sys, tempfile, textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import precheck

CASES = [
    ('P1 the same key twice in one function', '''
        def build(b):
            b.sketch('base', 'Base', plane, draw)
            b.extrude('base', 'Base extrude', s, NEW)
        ''', [3]),
    ('P2 if and else: only one runs', '''
        def build(b, big):
            if big:
                b.sketch('base', 'Base', plane, draw)
            else:
                b.sketch('base', 'Base', plane, draw_small)
        ''', []),
    ('P3 "if x:" then "if not x:", as in test_components.py', '''
        def build(b, x):
            if not x:
                b.sketch('a', 'A', plane, draw)
            if x:
                b.sketch('a', 'A', plane, draw)
        ''', []),
    ('P4 "==" then "!=" on the same thing', '''
        def build(b, mode):
            if mode == 'saved':
                b.step('a', 'A', make)
            if mode != 'saved':
                b.step('a', 'A', make)
        ''', []),
    ('P5 elif chain', '''
        def build(b, n):
            if n == 1:
                b.step('a', 'A', make)
            elif n == 2:
                b.step('a', 'A', make)
            else:
                b.step('a', 'A', make)
        ''', []),
    ('P6 two ifs on different questions: both can run', '''
        def build(b, x, y):
            if x:
                b.step('a', 'A', make)
            if y:
                b.step('a', 'A', make)
        ''', [5]),
    ('P7 same key in two functions: step() checks it at run time', '''
        def one(b):
            b.step('a', 'A', make)
        def two(b):
            b.step('a', 'A', make)
        ''', []),
    ('P8 two builders in one function', '''
        def build(b, c):
            b.step('a', 'A', make)
            c.step('a', 'A', make)
        ''', []),
    ('P9 twice-ok says why', '''
        def build(b, x):
            if x:
                b.step('a', 'A', make)
                return
            b.step('a', 'A', make)  # twice-ok: the one above returns
        ''', []),
    ('P10 a uses= key with a typo', '''
        def build(b):
            b.sketch('base_sketch', 'Base', plane, draw)
            b.extrude('base_extrude', 'Base', s, NEW, uses=['base_skecth'])
        ''', [3]),
    ('P11 a uses= key that fits a key built at run time', '''
        def build(b, key):
            b.sketch(key + '_sketch', 'Base', plane, draw)
            b.extrude('x', 'X', s, NEW, uses=['frame_sketch', 'frame_skecth'])
        ''', [3]),
    ('P12 a key from a variable: a uses= key written elsewhere in the file counts', '''
        def part(b, key):
            with b.component(key, 'Part'):
                pass
        def build(b):
            for k in ('left', 'right'):
                part(b, k)
            b.rect_pattern('p', 'P', lambda: [], ax, '2', 'd', ax, '1', 'd', uses=['right', 'rihgt'])
        ''', [7]),
    ('P13 shutil.copy and a vector copy are not steps', '''
        import shutil
        def build(b, v):
            shutil.copy('a.stl', 'b.stl')
            shutil.copy('a.stl', 'c.stl')
            w = v.copy()
        ''', []),
    ('P14 key and uses with % and f-strings', '''
        def build(b, n):
            for i in range(n):
                b.move('stud_%d_move' % i, 'Stud', bodies, 0, 0, 0)
                b.turn(f'stud_{i}_turn', 'Stud', bodies, ax, '90 deg')
            b.combine('join', 'Join', t, tools, J, uses=['stud_3_move', 'stud_3_turn', 'stud_3_mvoe'])
        ''', [5]),
    ('P15 a chamfer after a round in one function', '''
        def build(b):
            b.extrude('body', 'Body', s, NEW)
            b.fillet('rounds', 'Rounds', sets, uses=['body'])
            b.chamfer('bed', 'Bed chamfer', sets, uses=['rounds'])
        ''', [4]),
    ('P16 chamfer first, or marked, or in another function', '''
        def build(b):
            b.chamfer('bed', 'Bed chamfer', sets)
            b.fillet('rounds', 'Rounds', sets, uses=['bed'])
            b.chamfer('studs', 'Stud tops', sets, uses=['rounds'])  # round-first-ok: stud tops, not on the plate
        def other(b):
            b.chamfer('bed2', 'Bed chamfer', sets)
        def first(b):
            b.fillet('r2', 'Rounds', sets)
            with b.component('beam', 'Beam'):
                b.chamfer('beam_bed', 'Beam bed chamfer', sets)
        ''', []),
    ('P17 an STL exported straight through Fusion, not through write_stl', '''
        def stls(des, out):
            em = des.exportManager
            opts = em.createSTLExportOptions(body, 'part.stl')
            write_stl(des, out, body, 'part.stl')
        ''', [3]),
    ('P18 a fixed key inside a loop or a comprehension', '''
        def build(b, sk, n):
            for i in range(n):
                b.extrude('peg', 'Peg', sk, J)
                b.extrude('peg_%d' % i, 'Peg', sk, J)
            for s in [b.sketch('once', 'Once', plane, draw)]:
                pass
            pegs = [b.extrude('stud', 'Stud', sk, J) for i in range(n)]
            for i in range(n):
                b.extrude('last', 'Last', sk, J)  # twice-ok: n is always 1 here
        ''', [3, 7]),
    # A note, not a problem: the fourth item is the lines the note names.
    ('P19 a step function that reads a dict by key', '''
        def build(b, g, sk):
            d = g['cham']
            b.chamfer('edge', 'Edge', lambda: [(sk.edges(), g['cham'])])
            b.chamfer('edge2', 'Edge 2', lambda: [(sk.edges(), d)])
            b.chamfer('edge3', 'Edge 3', lambda e: [(e, e['size'])])
        ''', [], [3]),
]


def run():
    failed = 0
    with tempfile.TemporaryDirectory() as d:
        for name, src, want, *note in CASES:
            path = os.path.join(d, 'case.py')
            open(path, 'w').write(textwrap.dedent(src).lstrip('\n'))
            problems, notes = precheck.check(path)
            got = sorted(int(p.split(':')[1]) for p in problems)
            ok = got == sorted(want)
            if note:
                named = sorted(int(m) for n in notes if 'dict by key' in n for m in re.findall(r'(\d+) \(', n))
                ok = ok and named == note[0]
                if named != note[0]:
                    problems = problems + ['note names lines %s, want %s' % (named, note[0])]
            failed += not ok
            print('%s  %s' % ('ok  ' if ok else 'FAIL', name) + ('' if ok else '\n      want lines %s, got:\n      %s' % (want, '\n      '.join(problems) or 'nothing')))
    print('%d of %d failed' % (failed, len(CASES)) if failed else 'all %d passed' % len(CASES))
    return failed


if __name__ == '__main__':
    sys.exit(1 if run() else 0)
