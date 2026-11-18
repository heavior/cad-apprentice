# Finds Fusion calls that can take long but have no log line around them. Each one goes inside a
# `with cad_apprentice.slow(log, 'what'):` block, so a run that hangs names the call it hangs in
# (fusion/rules.md). Plain Python, no Fusion needed:
#   python3 lib/cad_apprentice/check_slow.py <file or folder>...
# A line that is fine without one says why in a "# slow-ok: <why>" comment. On a def line it covers the
# whole function, for a callback the caller already runs inside slow(). Folders skip run/ (old copies and
# probes). With --hook it reads a Claude Code PostToolUse event and checks the file just written.
import ast, json, os, sys

# Calls that make Fusion recompute, wait, or write a file.
CALLS = {'rollTo', 'moveToEnd', 'moveToBeginning', 'moveToNextStep', 'moveToPreviousStep', 'play', 'reorder',
         'deleteMe', 'save', 'saveAs', 'execute', 'computeAll', 'doEvents', 'modifyParameters', 'saveAsImageFile',
         'saveAsImageFileWithOptions', 'addSimple', 'addNewComponent', 'addByInsert'}
# Properties whose new value Fusion recomputes the design for.
SETS = {'expression', 'value', 'isSuppressed', 'markerPosition'}
# Collections whose add() Fusion computes before it returns, besides every *Features.
ADDS = {'constructionPlanes', 'constructionAxes', 'constructionPoints', 'sketches', 'joints', 'asBuiltJoints', 'documents'}
MARK = '# slow-ok:'


def _is_slow_block(node):
    for item in node.items:
        f = item.context_expr.func if isinstance(item.context_expr, ast.Call) else None
        if isinstance(f, ast.Name) and f.id == 'slow' or isinstance(f, ast.Attribute) and f.attr in ('slow', '_slow'):
            return True
    return False


def _call_name(node):
    f = node.func
    if not isinstance(f, ast.Attribute):
        return None
    if f.attr in CALLS:
        return f.attr
    # documents.open(dataFile), and Document.close(saveChanges); a file's close() takes no argument.
    if f.attr == 'open' and isinstance(f.value, ast.Attribute) and f.value.attr == 'documents':
        return 'documents.open'
    # A new feature or plane: Fusion computes it before add() returns.
    if f.attr == 'add' and isinstance(f.value, ast.Attribute) and (f.value.attr.endswith('Features') or f.value.attr in ADDS):
        return f.value.attr + '.add'
    if f.attr == 'close' and (node.args or node.keywords) and not (isinstance(f.value, ast.Name) and f.value.id == 'os'):
        return 'close'
    return None


def _targets(node):
    out = []
    for t in node.targets if isinstance(node, ast.Assign) else [node.target]:
        out += t.elts if isinstance(t, (ast.Tuple, ast.List)) else [t]
    return [t.attr for t in out if isinstance(t, ast.Attribute) and t.attr in SETS]


def check(path):
    text = open(path, encoding='utf-8').read()
    lines = text.splitlines()
    marked = lambda a, b: any(MARK in lines[i - 1] for i in range(a, (b or a) + 1))
    found = []

    def walk(node, inside):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and not isinstance(node, ast.Lambda):
            if MARK in lines[node.lineno - 1]:
                return
        if isinstance(node, (ast.With, ast.AsyncWith)) and _is_slow_block(node):
            inside = True
        what = None
        if isinstance(node, ast.Call):
            what = _call_name(node)
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            what = ', '.join('.%s =' % t for t in _targets(node)) or None
        if what and not inside and not marked(node.lineno, getattr(node, 'end_lineno', None)):
            found.append('%s:%d: %s outside slow()' % (path, node.lineno, what))
        for child in ast.iter_child_nodes(node):
            walk(child, inside)

    walk(ast.parse(text, path), False)
    return found


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


def fusion_script(path):
    # A Python file that talks to Fusion, itself or through the Builder. Other Python in the repo isn't checked.
    if not path.endswith('.py') or os.sep + 'run' + os.sep in path:
        return False
    text = open(path, encoding='utf-8').read()
    return 'adsk' in text or 'cad_apprentice' in text


if __name__ == '__main__':
    if sys.argv[1:] == ['--hook']:
        path = (json.load(sys.stdin).get('tool_input') or {}).get('file_path') or ''
        if not (os.path.isfile(path) and fusion_script(path)):
            sys.exit(0)
        found = check(path)
        if found:
            sys.stderr.write('Slow Fusion calls with no log line around them (fusion/rules.md, "A log line around every slow call"):\n'
                             + '\n'.join(found) + '\nWrap each in `with cad_apprentice.slow(log, ...)`, or say why not with "# slow-ok: <why>".\n')
            sys.exit(2)
        sys.exit(0)
    paths = list(files(sys.argv[1:]))
    checked = [p for p in paths if fusion_script(p)]
    found = [f for p in checked for f in check(p)]
    print('\n'.join(found) or 'no slow calls outside slow()')
    # Said, so "no slow calls" isn't read as covering files that weren't looked at.
    print('checked %d Fusion files, skipped %d other Python files' % (len(checked), len(paths) - len(checked)))
    sys.exit(1 if found else 0)
