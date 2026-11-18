# Reads a build script before its run changes the design, and finds step-key mistakes that would
# otherwise stop the run halfway, after Fusion has already done slow work (A5). A cheap check here
# saves time and tokens. Plain Python, no Fusion needed:
#   python3 fusion/lib/cad_apprentice/precheck.py <file or folder>...
# It finds:
#   - one step key written twice in one function, where both can run (step() would stop: "used twice");
#   - a key in uses= that no step in the script has: a typo, or a step that was renamed;
#   - a chamfer after a round in one function, on one builder and component: the build-plate chamfer goes before the
#     rounds (fusion/rules.md rule 11). A chamfer that isn't on the build plate says so in a
#     "# round-first-ok: <why>" comment on its line;
#   - as a note, not a problem: a function passed to a step that reads a dict by a fixed key
#     (lambda: g['width']), which the fingerprint can't see;
#   - an STL exported straight through Fusion instead of helpers.write_stl, which always uses High mesh
#     refinement, so no part gets printed from a coarse mesh.
# Keys built at run time (key + '_cut', 'stud_%d' % i) can't be read ahead. A uses= key is matched
# against them as a pattern, and the notes say how many there are, so a partial check is never silent.
# step() still checks every key as it runs. Two calls that can't both run in a way this can't see
# (an early return) say why in a "# twice-ok: <why>" comment on either line. Folders skip run/.
import ast, collections, os, re, sys

# Builder methods whose first argument is the key of a new step.
# A method added to Builder goes here too, or its keys go unchecked (fusion/rules.md rule 17).
STEPS = {'component', 'step', 'plane', 'sketch', 'extrude', 'combine', 'fillet', 'chamfer', 'base_body',
         'move', 'turn', 'copy', 'rect_pattern',
         'offset_plane', 'angled_plane', 'mid_plane', 'axis', 'point', 'revolve', 'sweep', 'pipe', 'loft', 'hole',
         'mirror', 'circular_pattern', 'path_pattern', 'split_body', 'shell', 'scale', 'remove',
         'joint', 'as_built_joint'}
MARK = '# twice-ok:'
ROUND_FIRST = '# round-first-ok:'


def _key(node):
    # A literal key as text, a run-time key as a regex, or None for something that isn't a key.
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return re.compile('^' + ''.join(re.escape(v.value) if isinstance(v, ast.Constant) else '.*' for v in node.values) + '$')
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _key(node.left), _key(node.right)
        if a is None and b is None:
            return None
        part = lambda k: '.*' if k is None else (k.pattern[1:-1] if isinstance(k, re.Pattern) else re.escape(k))
        return re.compile('^' + part(a) + part(b) + '$')
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
        return re.compile('^' + re.sub(r'%[-+ #0-9.]*[sdifr]', '.*', re.escape(node.left.value).replace(r'\%', '%')) + '$')
    return None


def _step_call(node, modules=()):
    # b.extrude('key', 'Name', ...): a step method, called with a key and a name. Other objects have
    # copy() and move() too, but not with a key first, and shutil.copy('a', 'b') is a module's.
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in STEPS):
        return False
    if isinstance(node.func.value, ast.Name) and node.func.value.id in modules:
        return False
    first = node.args[0] if node.args else None
    return len(node.args) >= 2 and (_key(first) is not None or isinstance(first, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)))


def _modules(tree):
    # Names the file imports, so shutil.copy() isn't read as a step.
    return {(a.asname or a.name).split('.')[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}


def _test(node):
    # An if's test as (text, True), with "not x", "a != b", "a is not b" and "a not in b" turned round.
    flip = {ast.NotEq: ast.Eq, ast.IsNot: ast.Is, ast.NotIn: ast.In}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        text, truth = _test(node.operand)
        return text, not truth
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in flip:
        return ast.unparse(ast.Compare(node.left, [flip[type(node.ops[0])]()], node.comparators)), False
    return ast.unparse(node), True


def _branches(path):
    # What must be true for a call to run: the side of each if it sits on, keyed by the if's test, so
    # "if x:" and a later "if not x:" count as two sides of one question. Also which except or case.
    out = {}
    for parent, child in zip(path, path[1:]):
        if isinstance(parent, (ast.If, ast.IfExp)):
            body = child in parent.body if isinstance(parent, ast.If) else child is parent.body
            orelse = child in parent.orelse if isinstance(parent, ast.If) else child is parent.orelse
            if body or orelse:
                text, truth = _test(parent.test)
                out[('if', text)] = truth if body else not truth
        elif isinstance(parent, ast.Try):
            if child in parent.handlers:
                out[('try', id(parent))] = 'handler %d' % parent.handlers.index(child)
            elif child in parent.orelse:
                out[('try', id(parent))] = 'else'
        elif isinstance(parent, ast.Match) and isinstance(child, ast.match_case):
            out[('match', id(parent))] = parent.cases.index(child)
    return out


def _apart(a, b):
    # True when two calls can't both run: they sit on different sides of one question.
    return any(k in b and b[k] != v for k, v in a.items())


def _repeats(node, child):
    # True when child, a node under node, can run more than once: a loop body or a comprehension's item.
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return child in node.body
    if isinstance(node, ast.While):
        return child in node.body or child is node.test
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        return not isinstance(child, ast.comprehension) or child is not node.generators[0]
    return False


def check(path, known=()):
    """Returns (problems, notes). known: keys from other files of the same run."""
    text = open(path, encoding='utf-8').read()
    lines = text.splitlines()
    marked = lambda n: any(MARK in lines[i - 1] for i in range(n.lineno, (n.end_lineno or n.lineno) + 1))
    calls = []  # (call, function it's in, path from that function down to it)
    uses = []  # (call, the uses= value)

    def walk(node, scope, path):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            scope, path = node, []
        path = path + [node]
        if _step_call(node, modules):
            calls.append((node, scope, path))
            for kw in node.keywords:
                if kw.arg == 'uses':
                    uses.append((node, kw.value))
        for child in ast.iter_child_nodes(node):
            walk(child, scope, path)

    tree = ast.parse(text, path)
    modules = _modules(tree)
    walk(tree, tree, [])
    problems, notes = [], []
    literal = {}
    patterns = []
    unread = 0  # Steps whose key is a variable, like b.component(key, name) in a helper.
    for call, scope, _ in calls:
        k = _key(call.args[0])
        if isinstance(k, str):
            literal.setdefault(k, []).append(call)
        elif k is None:
            unread += 1
        else:
            patterns.append(k)
    # A variable key came from somewhere: most often a text written elsewhere in the file, like the
    # list a loop goes over. So with one, a uses= key that is written outside uses= counts as found.
    texts = collections.Counter(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str))
    texts.subtract(n.value for _, v in uses for n in ast.walk(v) if isinstance(n, ast.Constant) and isinstance(n.value, str))
    elsewhere = {t for t, n in texts.items() if n > 0} if unread else set()

    # The same key twice in one function, on the same builder, where both can run.
    by_place = {}
    for call, scope, p in calls:
        k = _key(call.args[0])
        if isinstance(k, str):
            by_place.setdefault((id(scope), ast.unparse(call.func.value), k), []).append((call, _branches(p)))
    for (_, _, k), found in sorted(by_place.items(), key=lambda kv: kv[1][0][0].lineno):
        for i, (a, ba) in enumerate(found):
            for b, bb in found[i + 1:]:
                if not _apart(ba, bb) and not marked(a) and not marked(b):
                    problems.append('%s:%d: step key %r is also on line %d, and both can run: step() would stop with "used twice". '
                                    'If they can\'t both run, say why in a "%s <why>" comment' % (path, b.lineno, k, a.lineno, MARK))

    # A fixed key inside a loop in its own function: the second pass would stop with "used twice",
    # after the first one did the slow work.
    for call, scope, p in calls:
        k = _key(call.args[0])
        if isinstance(k, str) and not marked(call) and any(_repeats(n, nxt) for n, nxt in zip(p, p[1:])):
            problems.append('%s:%d: step key %r is fixed, but the step is in a loop: step() would stop with "used twice" '
                            'on the second pass. Put the loop value in the key, or say why it runs once in a "%s <why>" comment'
                            % (path, call.lineno, k, MARK))

    # A chamfer after a round, in the same function, builder and component, where both can run.
    lines = text.splitlines()
    by_builder = {}
    for call, scope, p in calls:
        if call.func.attr in ('fillet', 'chamfer'):
            comps = [n for n in p if isinstance(n, ast.With) and any(_step_call(i.context_expr, modules) and i.context_expr.func.attr == 'component' for i in n.items)]
            by_builder.setdefault((id(scope), ast.unparse(call.func.value), id(comps[-1]) if comps else None), []).append((call, _branches(p)))
    for found in by_builder.values():
        for a, ba in found:
            if a.func.attr != 'fillet':
                continue
            for c, bc in found:
                if c.func.attr == 'chamfer' and c.lineno > a.lineno and not _apart(ba, bc) and ROUND_FIRST not in lines[c.lineno - 1]:
                    problems.append('%s:%d: chamfer %s comes after the round on line %d. The build-plate chamfer goes before '
                                    'the rounds (fusion/rules.md rule 11); if this one isn\'t on the build plate, say so in a '
                                    '"%s <why>" comment' % (path, c.lineno, ast.unparse(c.args[0]), a.lineno, ROUND_FIRST))
                    break

    # A uses= key that no step has.
    skipped = 0
    for call, value in uses:
        items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else None
        if items is None:
            skipped += 1
            continue
        for item in items:
            if not (isinstance(item, ast.Constant) and isinstance(item.value, str)):
                skipped += 1
                continue
            u = item.value
            if u in literal or u in known or u in elsewhere or any(p.match(u) for p in patterns):
                continue
            problems.append('%s:%d: uses %r, but no step in the script has that key (a typo, or a step that was renamed?)'
                            % (path, item.lineno, u))
    if os.path.basename(path) != 'helpers.py':
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'createSTLExportOptions':
                problems.append('%s:%d: exports an STL straight through Fusion. Use helpers.write_stl(des, out, body, path), '
                                'which always exports at High mesh refinement.' % (path, n.lineno))
    # A function passed to a step that reads a dict by a fixed key: the fingerprint can't see that
    # value, so changing it doesn't rerun the step (lib/README.md, What the fingerprint can't see).
    blind = []
    for call, _, _ in calls:
        for arg in list(call.args[1:]) + [kw.value for kw in call.keywords]:
            for fn in ast.walk(arg):
                if not isinstance(fn, ast.Lambda):
                    continue
                own = {x.arg for x in fn.args.args + fn.args.kwonlyargs}
                for n in ast.walk(fn.body):
                    if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id not in own
                            and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str)):
                        blind.append('%d (%s)' % (n.lineno, ast.unparse(n)))
    if blind:
        notes.append('%s: %d step functions read a dict by key, which the fingerprint can\'t see, so a changed value '
                     'won\'t rerun the step; copy it into a plain variable first. Lines %s'
                     % (os.path.basename(path), len(blind), ', '.join(blind[:5]) + (', ...' if len(blind) > 5 else '')))
    if patterns or unread:
        notes.append('%s: %d step keys are built at run time and can\'t be read ahead; a uses= key that could be one counts as found'
                     % (os.path.basename(path), len(patterns) + unread))
    if skipped:
        notes.append('%s: %d uses= entries are built at run time; step() checks them as it runs'
                     % (os.path.basename(path), skipped))
    return problems, notes


def literal_keys(path):
    # Every step key written out in the file, for the next file of the same run.
    tree = ast.parse(open(path, encoding='utf-8').read(), path)
    modules = _modules(tree)
    return {n.args[0].value for n in ast.walk(tree) if _step_call(n, modules) and isinstance(_key(n.args[0]), str)}


HERE = os.path.dirname(os.path.abspath(__file__))


def read_ahead(read, visited, log):
    # Builder.step() calls this first. The first time a step comes from a script file, it reads that
    # file and stops the run on a problem, before any step from it has run. read maps each file read
    # this run to its keys; visited is the steps so far. Notes and a file it can't read go in the log.
    f = sys._getframe(1)
    while f is not None and os.path.dirname(os.path.abspath(f.f_code.co_filename)) == HERE:
        f = f.f_back
    path = f.f_code.co_filename if f is not None else None
    if path is None or path in read:
        return
    read[path] = set()
    try:
        known = set(visited).union(*read.values())
        problems, notes = check(path, known)
        read[path] = literal_keys(path)
    except (OSError, SyntaxError, ValueError) as e:
        log.append('read-ahead: couldn\'t read %s (%s), so step() checks its keys only as they run' % (path, e))
        return
    for n in notes:
        log.append('read-ahead: ' + n)
    if problems:
        raise Exception('read-ahead (fusion/rules.md): mistakes in %s, found before any of its steps ran:\n%s'
                        % (os.path.basename(path), '\n'.join(problems)))


# The .py files to check: each file given, and every .py file under each folder given
# (run/ and __pycache__/ skipped).
def files(args):
    for a in args:
        if os.path.isdir(a):
            for root, dirs, names in os.walk(a):
                dirs[:] = sorted(d for d in dirs if d not in ('run', '__pycache__'))
                for n in sorted(names):
                    if n.endswith('.py'):
                        yield os.path.join(root, n)
        else:
            yield a


if __name__ == '__main__':
    found = []
    for p in files(sys.argv[1:]):
        problems, notes = check(p)
        found += problems
        for n in notes:
            print('note: ' + n)
    print('\n'.join(found) or 'no problems found')
    sys.exit(1 if found else 0)
