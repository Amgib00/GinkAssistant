"""The server is one big module: a top-level name defined twice silently replaces the first one (0.1.153: a new
_NOT_A_NAME for patient names replaced the official-sources one). Extending a name with itself is fine."""
import ast
import os

SERVER = os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "services", "backend_server.py")


def test_no_top_level_name_is_defined_twice():
    tree = ast.parse(open(SERVER, encoding="utf-8").read())
    seen, twice = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names, extends = [node.name], set()
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            extends = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}   # X = X + (...): on purpose
        else:
            continue
        for name in names:
            if name in seen and name not in extends:
                twice.append(f"{name}: lines {seen[name]} and {node.lineno}")
            seen[name] = node.lineno
    assert twice == [], twice
