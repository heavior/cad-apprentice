# Ties the test plan to the tests, without Fusion: python3 check_plan_ids.py
# Lists the plan ids (upsert-test-scenarios.md § 3) that no scenario runs, and the
# scenarios the plan doesn't list. A plan entry that says "covered by", "planned" or "dropped" is
# accounted for. Exits 1 when either list has something in it.
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ACCOUNTED = ('covered by', 'planned', 'dropped')


def plan_ids():
    text = open(os.path.join(HERE, 'upsert-test-scenarios.md'), encoding='utf-8').read()
    part = text.split('## 3. Scenarios', 1)[1].split('\n## 4.', 1)[0]
    out = {}
    # An entry runs to the next bullet or heading, so a "covered by" on its second line counts.
    for m in re.finditer(r'^- \*\*([A-Z]\d+)\b(.*?)(?=^- |^#|\Z)', part, re.M | re.S):
        out[m.group(1)] = m.group(2)
    return out


def scenario_ids():
    text = open(os.path.join(HERE, 'upsert_scenarios.py'), encoding='utf-8').read()
    return [n.upper() for n in re.findall(r'^@scenario\ndef _?([a-z]\d+)\(S\)', text, re.M)]


def main():
    plan = plan_ids()
    code = set(scenario_ids())
    missing = sorted(p for p, rest in plan.items() if p not in code and not any(a in rest.lower() for a in ACCOUNTED))
    extra = sorted(c for c in code if c not in plan)
    print('%d plan ids, %d scenarios' % (len(plan), len(code)))
    print('in the plan, not run: %s' % (', '.join(missing) or 'none'))
    print('run, not in the plan: %s' % (', '.join(extra) or 'none'))
    return 1 if missing or extra else 0


if __name__ == '__main__':
    sys.exit(main())
