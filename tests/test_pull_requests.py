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
