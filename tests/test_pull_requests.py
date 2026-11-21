"""Pull requests: only collaborators; labels, assignee, milestone, reviews (CODEOWNERS)."""
import os
import subprocess
import yaml


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RECORD = yaml.safe_load(_read_text(os.path.join(ROOT, ".github", "workflows", "pull-requests.yml")))       # step 1
WF = yaml.safe_load(_read_text(os.path.join(ROOT, ".github", "workflows", "pull-request-triage.yml")))    # step 2


def _gate(tmp_path, author, permission):
    """Run the gate step with a fake gh: it answers the permission and records what it was asked to do."""
    step = next(s for s in WF["jobs"]["gate"]["steps"] if s.get("id") == "check")
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
    record = _read_text(os.path.join(ROOT, ".github", "workflows", "pull-requests.yml"))
    triage_text = _read_text(os.path.join(ROOT, ".github", "workflows", "pull-request-triage.yml"))
    for text in (record, triage_text):                 # pull_request_target: restricted by GitHub from 2 Dec 2026
        assert "pull_request_target:" not in text and "actions/checkout" not in text and "head.sha" not in text
    assert "gh pr edit" not in triage_text             # it asks about retired classic Projects and fails
    on = lambda wf: wf.get("on", wf.get(True))        # YAML 1.1 reads the key "on" as True
    assert on(RECORD) == {"pull_request": {"types": ["opened", "reopened", "ready_for_review", "synchronize"]}}
    assert RECORD["permissions"] == {"contents": "read"} and "secrets." not in record          # step 1: read-only
    assert on(WF)["workflow_run"]["workflows"] == [RECORD["name"]]
    which = next(s for s in WF["jobs"]["gate"]["steps"] if s.get("id") == "which")["run"]
    assert "tr -cd '0-9'" in which                     # the saved number is untrusted: digits only
    triage = WF["jobs"]["triage"]
    assert triage["needs"] == "gate" and "allowed == 'true'" in triage["if"]
    labeler = next(s for s in triage["steps"] if str(s.get("uses", "")).startswith("actions/labeler"))
    assert labeler["with"]["pr-number"] == "${{ needs.gate.outputs.pr }}"
    project = next(s for s in triage["steps"] if s.get("name") == "Add to the project")
    assert project["continue-on-error"] is True and "::warning::" in project["run"]          # "Bad credentials": a warning


def test_the_saved_number_is_checked(tmp_path):
    step = next(s for s in WF["jobs"]["gate"]["steps"] if s.get("id") == "which")
    out = tmp_path / "out.txt"
    for saved, want in (("12\nopened\n", ["pr=12", "action=opened"]), ("12; rm -rf /\n$(id)\n", ["pr=12", "action=synchronize"])):
        (tmp_path / "pr").mkdir(exist_ok=True)
        (tmp_path / "pr" / "pull-request.txt").write_text(saved)
        out.write_text("")
        subprocess.run(["bash", "-e", "-c", step["run"]], cwd=tmp_path, env={**os.environ, "GITHUB_OUTPUT": str(out)},
                       check=True, capture_output=True)
        assert out.read_text().split() == want


def test_reviews_labels_and_dependabot():
    assert "* @Amgib00" in open(os.path.join(ROOT, ".github", "CODEOWNERS")).read()            # review requested
    labels = yaml.safe_load(_read_text(os.path.join(ROOT, ".github", "labeler.yml")))
    assert {"app", "server", "web", "genie", "tests", "docs", "ci", "website", "dependencies"} <= set(labels)
    created = WF["jobs"]["triage"]["steps"][0]["run"]
    assert all(f"\n{name}|" in "\n" + created.split("<< 'LABELS'")[1] for name in labels)  # every label is created
    dep = yaml.safe_load(_read_text(os.path.join(ROOT, ".github", "dependabot.yml")))
    pip = dep["updates"][0]
    assert pip["labels"] == ["dependencies"] and pip["assignees"] == ["Amgib00"]
    ignored = {i["dependency-name"] for i in pip["ignore"]}
    assert {"webauthn", "cbor2", "cryptography", "numpy"} <= ignored        # the Intel-Mac pins stay put


def test_tidy_tool_previews_then_fixes_open_and_closed_pull_requests(tmp_path):
    import json
    import sys
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
elif a[:2] == ["pr", "edit"]:          # like the owner's gh: classic Projects are retired
    sys.stderr.write("GraphQL: Projects (classic) is being deprecated (repository.pullRequest.projectCards)\\n"); sys.exit(1)
elif a[:1] == ["api"] and "milestones?state=open" in a[1]:
    print("")
elif a[:1] == ["api"] and a[1].endswith("/milestones"):
    print("7")
""" % str(tmp_path))
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}
    tool = os.path.join(ROOT, "tools", "tidy_pull_requests.py")
    out = subprocess.run([sys.executable, tool], env=env, capture_output=True, text=True, check=True).stdout
    assert "would be updated" in out and "pr edit" not in log.read_text()            # the preview changes nothing
    log.write_text("")
    subprocess.run([sys.executable, tool, "--apply"], env=env, capture_output=True, text=True, check=True)
    calls = log.read_text()
    assert "api -X POST repos/Amgib00/GinkAssistant/issues/24/labels -f labels[]=dependencies -f labels[]=server" in calls
    assert "api -X POST repos/Amgib00/GinkAssistant/issues/24/assignees -f assignees[]=Amgib00" in calls
    assert "api -X PATCH repos/Amgib00/GinkAssistant/issues/24 -F milestone=7" in calls
    assert "issues/6/labels -f labels[]=server -f labels[]=tests" in calls and "issues/6 -F milestone" not in calls   # closed: no milestone
    assert "issues/5/" not in calls and "pr edit" not in calls                           # already tidy; never gh pr edit
    assert calls.count("label create") == 9 and "milestones -f title=Next release" in calls
    assert "pr close" not in calls and "pr merge" not in calls and "pr reopen" not in calls


def test_autofix_pull_requests_of_fixed_alerts_are_closed(tmp_path):
    """tools/close_fixed_alert_prs.py: Copilot Autofix's old pull requests -- closed when their alert is fixed or
    dismissed, kept (and listed with where the alert is) while it's still open."""
    import json
    import sys
    prs = [{"number": 36, "title": "Potential fix for code scanning alert no. 1383: Client-side URL redirect"},
           {"number": 34, "title": "Potential fix for code scanning alert no. 1356: Information exposure through an exception"},
           {"number": 49, "title": "Potential fix for code scanning alert no. 1362: Workflow does not contain permissions"},
           {"number": 53, "title": "Bump the python-dependencies group with 6 updates"}]
    alerts = {"1383": {"state": "fixed"}, "1362": {"state": "dismissed"},
              "1356": {"state": "open", "rule": {"description": "Information exposure through an exception"},
                       "most_recent_instance": {"location": {"path": "src/x.py", "start_line": 12}}}}
    (tmp_path / "bin").mkdir()
    (tmp_path / "prs.json").write_text(json.dumps(prs)); (tmp_path / "alerts.json").write_text(json.dumps(alerts))
    fake = tmp_path / "bin" / "gh"
    fake.write_text("#!" + sys.executable + """
import json, sys
d = %r
a = sys.argv[1:]
open(d + "/gh.log", "a").write(" ".join(a) + "\\n")
if a[:2] == ["pr", "list"]:
    print(open(d + "/prs.json").read())
elif a[:1] == ["api"] and "/code-scanning/alerts/" in a[1]:
    print(json.dumps(json.load(open(d + "/alerts.json"))[a[1].rsplit("/", 1)[1]]))
""" % str(tmp_path))
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}
    tool = os.path.join(ROOT, "tools", "close_fixed_alert_prs.py")
    out = subprocess.run([sys.executable, tool], env=env, capture_output=True, text=True, check=True).stdout
    assert "2 pull request(s) would be closed; 1 kept." in out and "pr close" not in (tmp_path / "gh.log").read_text()
    assert "alert 1356: Information exposure through an exception at src/x.py:12  (pull request #34)" in out
    out = subprocess.run([sys.executable, tool, "--close"], env=env, capture_output=True, text=True, check=True).stdout
    closed = [l.split()[2] for l in (tmp_path / "gh.log").read_text().splitlines() if l.startswith("pr close")]
    assert sorted(closed) == ["36", "49"] and "53" not in closed                   # never the open alert or other PRs
