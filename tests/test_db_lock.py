"""The server's database lock (_db_lock) is a plain threading.Lock: taking it twice in one thread waits
forever -- that request hangs, and so does every later database call (sign-ins, chats...) until a
restart. 0.1.117's usage download nearly shipped that. This reads the server's code and fails if any
`with _db_lock:` block calls a function that takes the lock itself, directly or through other helpers."""
import ast
import os

SERVER = os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "services", "backend_server.py")


def _with_lock(fn):
    return [w for w in ast.walk(fn) if isinstance(w, (ast.With, ast.AsyncWith))
            and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_db_lock" for i in w.items)]


def _local_names(fn):
    """Names a function defines itself (arguments, assignments, inner functions): calls to them aren't the
    module's functions of the same name."""
    names = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
    for n in ast.walk(fn):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn:
            names.add(n.name)
        elif isinstance(n, ast.Assign):
            names |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    return names


def _calls(node, local):
    return {c.func.id for c in ast.walk(node)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id not in local}


def test_no_function_takes_the_database_lock_twice():
    tree = ast.parse(open(SERVER, encoding="utf-8").read())
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    takes = {name for name, fn in funcs.items() if _with_lock(fn)}
    grew = True
    while grew:                                            # calling a lock-taker means taking the lock
        grew = False
        for name, fn in funcs.items():
            if name not in takes and _calls(fn, _local_names(fn)) & takes:
                takes.add(name)
                grew = True
    assert len(takes) > 50                                # the scan really sees the server's helpers
    nested = []
    for name, fn in funcs.items():
        local = _local_names(fn)
        for w in _with_lock(fn):
            bad = set().union(*(_calls(stmt, local) for stmt in w.body)) & takes
            if bad:
                nested.append(f"{name} (line {w.lineno}) calls {sorted(bad)} while holding _db_lock")
    assert nested == [], "\n".join(nested)
