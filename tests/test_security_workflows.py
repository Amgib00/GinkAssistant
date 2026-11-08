"""Security checks that can't fail for lack of a paid account, and closing the scanner pull requests that can."""
import os, shutil, subprocess
import pytest
yaml = pytest.importorskip("yaml")
ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_free_security_workflow():
    wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "security.yml"), encoding="utf-8"))
    jobs = wf["jobs"]
    hado = [s for s in jobs["dockerfile"]["steps"] if s.get("uses", "").startswith("hadolint/")][0]
    assert hado["with"]["dockerfile"] == "deploy/Dockerfile" and hado["with"]["no-fail"] is True
    assert jobs["dockerfile"]["permissions"]["security-events"] == "write"
    assert "pip-audit -r deploy/requirements-server.txt" in jobs["packages"]["steps"][-1]["run"]
    text = open(os.path.join(ROOT, ".github", "workflows", "security.yml"), encoding="utf-8").read()
    assert "secrets." not in text                                              # nothing a fork or a new repo lacks
    names = os.listdir(os.path.join(ROOT, ".github", "workflows"))
    assert not any(n.startswith(("codeql", "codacy", "snyk", "checkmarx", "fortify", "sysdig", "apisec", "black-duck",
                                 "psscriptanalyzer")) for n in names)          # CodeQL: the default setup instead


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="needs bash")
def test_closing_only_the_scanner_prs(tmp_path):
    gh = tmp_path / "gh"
    log = tmp_path / "log"
    gh.write_text("#!/bin/bash\n"
                  "if [ \"$1 $2\" = \"pr list\" ]; then printf '12\\tc\\tAdd Codacy security scan workflow\\n"
                  "13\\ts\\tCreate snyk-security.yml\\n20\\tf\\tAdd Fortify AST Scan workflow\\n14\\tt\\tFix a typo\\n'\n"
                  f"elif [ \"$1 $2\" = \"pr close\" ]; then echo \"$3\" >> {log}; fi\n")
    gh.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}")
    dry = subprocess.run(["bash", "tools/close_scanner_prs.sh"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert "would close #12" in dry.stdout and "#14" not in dry.stdout and not log.exists()
    subprocess.run(["bash", "tools/close_scanner_prs.sh", "--close"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert log.read_text().split() == ["12", "13", "20"]                         # the typo fix stays open
