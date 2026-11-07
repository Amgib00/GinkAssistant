"""Genie on real repositories: edit part of a file, find files by name, read long files in numbered
parts, search with regular expressions, and open a GitHub repository."""
import io
import os
import sys
import zipfile
sys.path.insert(0, os.path.dirname(__file__))
import httpx


def project(b, c, h, files):
    pid = c.post("/genie/projects", headers=h, json={"name": "repo"}).json()["project"]["id"]
    for path, content in files.items():
        b._genie_write(pid, path, content)
    return pid


def test_edit_file_changes_exactly_one_place(genie_srv):
    b, c, h = genie_srv
    pid = project(b, c, h, {"src/app.py": "def total(xs):\n    return sum(xs)\n\nprint(total([1, 2]))\n"})
    changes = []
    out = b._genie_tool(pid, "edit_file", {"path": "src/app.py", "old_text": "return sum(xs)",
                                           "new_text": "return sum(x for x in xs if x)"}, changes)
    assert out == "Changed src/app.py at line 2." and changes == [{"path": "src/app.py", "action": "changed"}]
    assert "if x)" in b._genie_files(pid)["src/app.py"]
    assert "found 0 times" in b._genie_tool(pid, "edit_file", {"path": "src/app.py", "old_text": "nope", "new_text": "x"}, [])
    b._genie_write(pid, "twice.txt", "a\na\n")
    assert "found 2 times" in b._genie_tool(pid, "edit_file", {"path": "twice.txt", "old_text": "a", "new_text": "b"}, [])
    assert "No text file" in b._genie_tool(pid, "edit_file", {"path": "missing.py", "old_text": "a", "new_text": "b"}, [])


def test_find_files_and_regex_search(genie_srv):
    b, c, h = genie_srv
    pid = project(b, c, h, {"README.md": "# Repo", "src/app.py": "import os\nTOKEN = os.environ['X']\n",
                            "src/util/helpers.py": "def helper():\n    pass\n", "tests/test_app.py": "def test_ok():\n    assert True\n",
                            "web/[id].tsx": "export default 1"})
    assert b._genie_tool(pid, "find_files", {"pattern": "*.py"}, []).split("\n") == \
        ["src/app.py", "src/util/helpers.py", "tests/test_app.py"]
    assert b._genie_tool(pid, "find_files", {"pattern": "src/**/*.py"}, []).split("\n") == ["src/app.py", "src/util/helpers.py"]
    assert b._genie_tool(pid, "find_files", {"pattern": "*test*"}, []) == "tests/test_app.py"
    assert "web/[id].tsx" in b._genie_tool(pid, "find_files", {"pattern": "*.tsx"}, [])        # real-repo file names
    out = b._genie_tool(pid, "search_files", {"text": r"def \w+\(", "regex": True, "path_pattern": "src/**/*.py"}, [])
    assert out == "src/util/helpers.py:1: def helper():"
    assert "doesn't work" in b._genie_tool(pid, "search_files", {"text": "(", "regex": True}, [])


def test_long_files_read_in_numbered_parts(genie_srv):
    b, c, h = genie_srv
    pid = project(b, c, h, {"big.py": "\n".join(f"line {i}" for i in range(1, 1001))})
    first = b._genie_tool(pid, "read_file", {"path": "big.py"}, [])
    assert first.startswith("  1| line 1") and "[lines 1-400 of 1000" in first
    part = b._genie_tool(pid, "read_file", {"path": "big.py", "start_line": 990, "end_line": 1000}, [])
    assert part.startswith(" 990| line 990") and part.split("\n")[-2].endswith("line 1000")


def zipball(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p, t in files.items():
            z.writestr("owner-repo-abc123/" + p, t)
    return buf.getvalue()


def test_open_a_github_repository(genie_srv, monkeypatch):
    b, c, h = genie_srv
    from httpx import _client
    seen = []
    data = zipball({"README.md": "# Hello", "src/main.py": "print('hi')", "node_modules/x/index.js": "skip me"})

    def github(request):
        seen.append((str(request.url), request.headers.get("authorization")))
        if "missing" in str(request.url):
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, content=data)

    class Mock(_client.AsyncClient):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(github); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    pid = c.post("/genie/projects", headers=h, json={"name": "repo"}).json()["project"]["id"]
    r = c.post(f"/genie/projects/{pid}/import", headers=h, json={"github": "https://github.com/owner/repo/tree/dev"})
    assert r.status_code == 200 and sorted(r.json()["imported"]) == ["README.md", "src/main.py"]
    assert seen[-1] == ("https://api.github.com/repos/owner/repo/zipball/dev", None)       # public: no token
    r = c.post(f"/genie/projects/{pid}/import", headers=h, json={"github": "owner/missing"})
    assert r.status_code == 404 and "connect GitHub" in r.json()["detail"]
    r = c.post(f"/genie/projects/{pid}/import", headers=h, json={"github": "not a repo; rm -rf"})
    assert r.status_code == 422
    monkeypatch.setattr(b, "GITHUB_ZIP_MAX", 50)
    r = c.post(f"/genie/projects/{pid}/import", headers=h, json={"github": "owner/repo"})
    assert r.status_code == 422 and "too large" in r.json()["detail"]


def test_page_opens_pasted_github_links():
    page = open(os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "services", "web_app", "genie.html"),
                encoding="utf-8").read()
    assert "function githubRepo(" in page and "importGithub(repo" in page and "paste a GitHub link" in page
