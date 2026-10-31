"""Pull requests: only collaborators; labels, assignee, milestone, reviews (CODEOWNERS)."""
import os, subprocess
import yaml
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WF = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "pull-requests.yml")))


def _gate(tmp_path, author, permission):
    """Run the gate step with a fake gh: it answers the permission and records what it was asked to do."""
    step = WF["jobs"]["gate"]["steps"][0]
    log = tmp_path / "gh.log"; out = tmp_path / "out.txt"; out.write_text("")
    (tmp_path / "bin").mkdir(exist_ok=True)
    gh = tmp_path / "bin" / "gh"
    gh.write_text('#!/bin/bash\necho "$*" >> "%s"\n[ "$1" = api ] && echo "%s"\nexit 0\n' % (log, permission))
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "REPO": "Amgib00/GinkAssistant", "PR": "7",
           "AUTHOR": author, "OWNER": "Amgib00", "GITHUB_OUTPUT": str(out), "GH_TOKEN": "x"}
    subprocess.run(["bash", "-e", "-c", step["run"]], env=env, check=True, capture_output=True)
    return out.read_text().strip(), (log.read_text() if log.exists() else "")


def test_only_collaborators_may_open_pull_requests(tmp_path):
    allowed, calls = _gate(tmp_path, "stranger42", "read")
    assert allowed == "allowed=false" and "pr close 7" in calls and "pr comment 7" in calls
    for who, perm in (("helper", "write"), ("Amgib00", "admin"), ("dependabot[bot]", "none")):
        (tmp_path / "gh.log").unlink(missing_ok=True)
        allowed, calls = _gate(tmp_path, who, perm)
        assert allowed == "allowed=true" and "close" not in calls, who


def test_the_workflow_never_runs_the_pull_requests_code():
    text = open(os.path.join(ROOT, ".github", "workflows", "pull-requests.yml")).read()
    assert "pull_request_target" in text and "actions/checkout" not in text and "head.sha" not in text
    triage = WF["jobs"]["triage"]
    assert triage["needs"] == "gate" and "allowed == 'true'" in triage["if"]


def test_reviews_labels_and_dependabot():
    assert "* @Amgib00" in open(os.path.join(ROOT, ".github", "CODEOWNERS")).read()            # review requested
    labels = yaml.safe_load(open(os.path.join(ROOT, ".github", "labeler.yml")))
    assert {"app", "server", "web", "genie", "tests", "docs", "ci", "website", "dependencies"} <= set(labels)
    created = WF["jobs"]["triage"]["steps"][0]["run"]
    assert all(f"\n{name}|" in "\n" + created.split("<< 'LABELS'")[1] for name in labels)  # every label is created
    dep = yaml.safe_load(open(os.path.join(ROOT, ".github", "dependabot.yml")))
    pip = dep["updates"][0]
    assert pip["labels"] == ["dependencies"] and pip["assignees"] == ["Amgib00"]
    ignored = {i["dependency-name"] for i in pip["ignore"]}
    assert {"webauthn", "cbor2", "cryptography", "numpy"} <= ignored        # the Intel-Mac pins stay put


def test_tidy_tool_previews_then_fixes_open_and_closed_pull_requests(tmp_path):
    import json, sys
    prs = [{"number": 24, "title": "Bump the python-dependencies group", "state": "OPEN", "labels": [], "assignees": [], "milestone": None},
           {"number": 5, "title": "Docs", "state": "MERGED", "labels": [{"name": "docs"}], "assignees": [{"login": "Amgib00"}], "milestone": None},
           {"number": 6, "title": "Server fix", "state": "CLOSED", "labels": [], "assignees": [], "milestone": None}]
    files = {"24": ["requirements.txt", "deploy/requirements-server.txt"], "5": ["README.md"], "6": ["src/ginkassistant/services/backend_server.py", "tests/test_x.py"]}
    log = tmp_path / "gh.log"
    (tmp_path / "bin").mkdir()
    fake = tmp_path / "bin" / "gh"
    (tmp_path / "prs.json").write_text(json.dumps(prs)); (tmp_path / "files.json").write_text(json.dumps(files))
    fake.write_text("#!" + sys.executable + """
import json, sys
d = %r
a = sys.argv[1:]
open(d + "/gh.log", "a").write(" ".join(a) + "\\n")
if a[:2] == ["pr", "list"]:
    print(open(d + "/prs.json").read())
elif a[:2] == ["pr", "view"]:
    print(json.dumps({"files": [{"path": x} for x in json.load(open(d + "/files.json"))[a[2]]]}))
elif a[:1] == ["api"] and "milestones?state=open" in a[1]:
    print("")
""" % str(tmp_path))
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}
    tool = os.path.join(ROOT, "tools", "tidy_pull_requests.py")
    out = subprocess.run([sys.executable, tool], env=env, capture_output=True, text=True, check=True).stdout
    assert "would be updated" in out and "pr edit" not in log.read_text()            # the preview changes nothing
    log.write_text("")
    subprocess.run([sys.executable, tool, "--apply"], env=env, capture_output=True, text=True, check=True)
    calls = log.read_text()
    assert "pr edit 24 -R Amgib00/GinkAssistant --add-label dependencies,server --add-assignee Amgib00 --milestone Next release" in calls
    assert "pr edit 6 -R Amgib00/GinkAssistant --add-label server,tests --add-assignee Amgib00" in calls   # closed: no milestone
    assert "pr edit 5 " not in calls                                                     # already tidy
    assert calls.count("label create") == 9 and "milestones -f title=Next release" in calls
    assert "pr close" not in calls and "pr merge" not in calls and "pr reopen" not in calls
