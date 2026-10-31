"""The publish script and the Release check, run for real (Releases #19-#33 failed on these).
- Pasting the whole update block must work: the publish script may not ask questions by default
  (a question swallowed the next pasted line -> "Nothing pushed." -> Release ran on old code).
- Release must accept no version (use pyproject.toml) and explain a stale version clearly."""
import os, shutil, subprocess, sys
import pytest
yaml = pytest.importorskip("yaml")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
pytestmark = pytest.mark.skipif(shutil.which("git") is None or os.name == "nt", reason="needs git and bash")


def sh(cmd, cwd, **env):
    return subprocess.run(["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True, timeout=240, env={**os.environ, **env})


def version_of(path):
    for line in open(os.path.join(path, "pyproject.toml")):
        if line.startswith("version"):
            return line.split('"')[1]


def test_publish_works_when_the_whole_block_is_pasted(tmp_path):
    fake = tmp_path / "github.git"
    sh(f"git init -q --bare {fake} && git -C {fake} symbolic-ref HEAD refs/heads/main", tmp_path)   # git < 2.28 has no -b
    seed = tmp_path / "seed"; seed.mkdir()
    sh("git init -q && git checkout -q -b main && printf '[project]\\nversion = \"0.0.1\"\\n' > pyproject.toml && echo MIT > LICENSE && "
       "git add -A && git -c user.email=t@t -c user.name=t commit -qm old && git push -q " + str(fake) + " main", seed)
    work = tmp_path / "gink"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git", "*.egg-info"))
    pasted = "gh workflow run release.yml -R x/y -f version=v9.9.9\necho next\n"           # the lines after it
    r = subprocess.run(["bash", "tools/publish_to_github.sh"], cwd=work, input=pasted, capture_output=True, text=True, timeout=240,
                       env={**os.environ, "GINK_REPO": str(fake), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    v = version_of(work)
    assert f"GitHub now has version {v}." in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
    assert "Nothing pushed" not in r.stdout
    shown = sh(f"git --git-dir={fake} show main:pyproject.toml", tmp_path).stdout
    assert f'version = "{v}"' in shown
    assert sh(f"git --git-dir={fake} log -1 --format=%s main", tmp_path).stdout.strip() == f"Gink {v}"


def test_release_check_step(tmp_path):
    if subprocess.run(["python3", "-c", "import tomllib"], capture_output=True).returncode != 0:
        pytest.skip("the release check runs on GitHub with Python 3.11+ as python3; this computer's python3 is older")
    wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "release.yml")))
    step = [s for s in wf["jobs"]["check"]["steps"] if s.get("id") == "v"][0]
    assert "check" in wf["jobs"]["publish"]["needs"]                               # it reads check's version
    assert wf["concurrency"] == {"group": "release", "cancel-in-progress": False}  # one release at a time (#34/#35)
    assert "was released by another run" in wf["jobs"]["publish"]["steps"][-1]["run"]
    (tmp_path / "check.sh").write_text(step["run"])
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n')
    (tmp_path / "CHANGELOG.md").write_text("## 1.2.3 (x)\n")
    (tmp_path / "bin").mkdir(); gh = tmp_path / "bin" / "gh"
    gh.write_text('#!/bin/bash\n[ "$1 $2 $3" = "release view v1.2.2" ] && exit 0 || exit 1\n'); gh.chmod(0o755)
    def run(version):
        out = tmp_path / "out.txt"; out.write_text("")
        r = sh("bash -e check.sh", tmp_path, VERSION=version, GITHUB_OUTPUT=str(out), GITHUB_REPOSITORY="x/y",
               PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}")
        return r.returncode, r.stdout + r.stderr, out.read_text().strip()
    assert run("")[0] == 0 and run("")[2] == "version=v1.2.3"                      # no version: pyproject.toml's
    assert run("v1.2.3")[2] == "version=v1.2.3"
    code, log, _ = run("v1.2.2")                                                     # an old command
    assert code == 1 and "wasn't published yet" in log and "publish_to_github.sh" in log
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.2"\n')
    code, log, _ = run("")
    assert code == 1 and "already released" in log
