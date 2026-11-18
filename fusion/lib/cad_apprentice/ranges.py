# Parameter ranges: the values a plain-value parameter is meant to take, low to high in steps. The
# parameter test tries them, and the same numbers are the slider limits on MakerWorld's Customize page.
# Plain Python, no Fusion, so test_ranges.py runs anywhere.
import re


def number(expr, unit):
    # '12.5 mm' -> 12.5. A bare number takes the parameter's unit. None if it isn't a plain value in that unit.
    m = re.fullmatch(r'\s*(-?[0-9]*\.?[0-9]+)\s*([a-zA-Z]*)\s*', str(expr))
    if not m or (m.group(2) and m.group(2) != (unit or '')):
        return None
    return float(m.group(1))


# 12.5, 'mm' -> '12.5 mm'.
def text(n, unit):
    return ('%g %s' % (round(n, 6), unit or '')).strip()


def check(name, expr, unit, low, high, step):
    # The range as numbers (low, high, step). Raises when it can't be used: a formula, a value in
    # another unit, low not below high, a step that doesn't fit, or a value outside the range.
    if step is None and not unit:
        step = 1
    if step is None:
        raise Exception('parameter %s has a range but no step. Give step= too, the size a slider moves by.' % name)
    nums = [number(x, unit) for x in (expr, low, high, step)]
    if nums[0] is None:
        raise Exception('parameter %s = %s has a range, but only a plain value can have one' % (name, expr))
    for x, n in zip((low, high, step), nums[1:]):
        if n is None:
            raise Exception('parameter %s: range value %r is not a plain number in %s' % (name, x, unit or 'no unit'))
    v, lo, hi, st = nums
    if not lo < hi or st <= 0:
        raise Exception('parameter %s: range %s to %s step %s goes nowhere. Low must be below high, and the step above 0.'
                        % (name, text(lo, unit), text(hi, unit), text(st, unit)))
    if not _on_grid(hi, lo, st):
        raise Exception('parameter %s: the range %s to %s is not a whole number of %s steps'
                        % (name, text(lo, unit), text(hi, unit), text(st, unit)))
    if not lo - 1e-9 <= v <= hi + 1e-9 or not _on_grid(v, lo, st):
        raise Exception('parameter %s = %s is not one of the range\'s values, %s to %s in %s steps'
                        % (name, expr, text(lo, unit), text(hi, unit), text(st, unit)))
    return lo, hi, st


def _on_grid(v, lo, st):
    k = (v - lo) / st
    return abs(k - round(k)) < 1e-6


# Every value from lo to hi in steps of st.
def grid(lo, hi, st):
    return [lo + k * st for k in range(int(round((hi - lo) / st)) + 1)]


# The range as the text kept on the parameter; load() reads it back.
def store(lo, hi, st):
    return '%r;%r;%r' % (lo, hi, st)


# The (low, high, step) that store() wrote.
def load(value):
    lo, hi, st = (float(x) for x in value.split(';'))
    return lo, hi, st
