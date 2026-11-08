"""The server runs on Render from deploy/Dockerfile, which copies backend_server.py and a few helper modules
FLAT into /srv -- not as the ginkassistant package. A helper imported only the package way (`from . import x`)
works in every other test but breaks there: 0.1.111's blob_store did that, so /health failed on Render and so
did every deploy after it. These tests rebuild that flat layout and use it."""
import ast
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
SERVER = os.path.join(ROOT, "src", "ginkassistant", "services", "backend_server.py")


def _copies():
    """(source, target) for each `COPY src/... ./...` in the Dockerfile."""
    text = open(os.path.join(ROOT, "deploy", "Dockerfile"), encoding="utf-8").read()
    return re.findall(r"^COPY (src/\S+) (\./\S+)$", text, re.M)


def test_every_package_import_has_the_flat_fallback():
    """`from .x import y` must sit in a try whose `except ImportError` imports x the plain way."""
    tree = ast.parse(open(SERVER, encoding="utf-8").read())
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            handled = any(isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "ModuleNotFoundError")
                          for h in node.handlers)
            for stmt in node.body:
                if isinstance(stmt, ast.ImportFrom) and stmt.level and handled:
                    stmt._ok = True
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level and not getattr(node, "_ok", False):
            bad.append(f"line {node.lineno}: from {'.' * node.level}{node.module or ''} import ...")
    assert bad == [], "\n".join(bad)


def test_every_imported_helper_is_copied_into_the_image():
    tree = ast.parse(open(SERVER, encoding="utf-8").read())
    local = {os.path.splitext(f)[0] for f in os.listdir(os.path.dirname(SERVER)) if f.endswith(".py")}
    needed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            needed.add(node.module or node.names[0].name)
        elif isinstance(node, ast.ImportFrom) and node.module in local:
            needed.add(node.module)
        elif isinstance(node, ast.Import):
            needed |= {a.name for a in node.names if a.name in local}
    copied = {os.path.splitext(os.path.basename(t))[0] for _s, t in _copies()}
    assert needed - {"backend_server"} <= copied, f"not copied by deploy/Dockerfile: {sorted(needed - copied)}"


def test_the_server_works_laid_out_like_the_image(tmp_path):
    srv = tmp_path / "srv"
    srv.mkdir()
    for source, target in _copies():
        src = os.path.join(ROOT, source)
        dst = srv / target[2:]
        shutil.copytree(src, dst) if os.path.isdir(src) else shutil.copy(src, dst)
    script = r'''
import os, sys
from fastapi.testclient import TestClient
import backend_server as b
c = TestClient(b.app)
assert c.get("/health").status_code == 200, "health"
assert c.get("/info").status_code == 200, "info"
assert c.get("/app").status_code == 200, "web app"
marker = b._genie_store_content("x = 1\n" * 3000)                  # the blob store, flat
assert marker.startswith(b.GENIE_BLOB) and b._genie_resolve(marker).startswith("x = 1"), "blob store"
assert c.post("/errors", json={"kind": "E", "stack": "x"}).json()["ok"] is True, "errors"
print("OK")
'''
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
    env.update(GINK_DB_PATH=str(tmp_path / "db" / "gink.db"), PYTHONPATH=str(srv))
    r = subprocess.run([sys.executable, "-c", script], cwd=srv, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout[-1500:] + r.stderr[-2500:]
