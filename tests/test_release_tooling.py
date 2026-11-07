"""The publish script and the Release check, run for real (Releases #19-#33 failed on these).
- Pasting the whole update block must work: the publish script may not ask questions by default
  (a question swallowed the next pasted line -> "Nothing pushed." -> Release ran on old code).
- Release must accept no version (use pyproject.toml) and explain a stale version clearly."""
import os
import shutil
import subprocess
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


def test_releases_are_test_builds_unless_for_users():
    """Not every push reaches users: a release is a GitHub pre-release (test build) unless for_users=true.
    The apps' update offer (/app/version) and the website use releases/latest, which skips pre-releases."""
    wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "release.yml")))
    inp = wf[True]["workflow_dispatch"]["inputs"]["for_users"]
    assert inp["type"] == "boolean" and inp["default"] is False
    run = next(s["run"] for s in wf["jobs"]["publish"]["steps"] if s.get("name") == "Publish the release")
    test_build, for_users = run.split('if [ "$FOR_USERS" = "true" ]; then', 1)[1].split("else", 1)
    assert "--latest" in test_build and "--prerelease" not in test_build
    assert "--prerelease --latest=false" in for_users
    src = open(os.path.join(ROOT, "src", "ginkassistant", "services", "backend_server.py"), encoding="utf-8").read()
    assert "/releases/latest" in src                                    # GitHub leaves pre-releases out of "latest"


def _project_with_git(tmp_path):
    """A fake GitHub with an old version, and the owner's project folder: a Git clone of it whose files are the
    new version (unzipped over it) -- exactly the owner's Mac."""
    fake = tmp_path / "github.git"
    sh(f"git init -q --bare {fake} && git -C {fake} symbolic-ref HEAD refs/heads/main", tmp_path)
    seed = tmp_path / "seed"; seed.mkdir()
    sh("git init -q && git checkout -q -b main && printf '[project]\\\\nversion = \\\"0.0.1\\\"\\\\n' > pyproject.toml && echo MIT > LICENSE && "
       "git add -A && git -c user.email=t@t -c user.name=t commit -qm old && git push -q " + str(fake) + " main", seed)
    work = tmp_path / "gink"
    sh(f"git clone -q {fake} {work}", tmp_path)
    shutil.copytree(ROOT, work, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git", "*.egg-info", ".ruff_cache"))
    env = {"GINK_REPO": str(fake), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return fake, work, env


def test_publish_brings_the_project_folders_git_along(tmp_path):
    """PyCharm showed thousands of "Potential merge conflicts detected": the folder's Git stayed on an old
    version while every file was changed both here and on GitHub."""
    fake, work, env = _project_with_git(tmp_path)
    assert " M pyproject.toml" in sh("git status --porcelain", work).stdout              # before: changed here and there
    r = sh("bash tools/publish_to_github.sh", work, **env)
    assert "no more merge-conflict warnings" in r.stdout, r.stdout[-1500:] + r.stderr[-500:]
    head = sh("git rev-parse HEAD", work).stdout.strip()
    assert head == sh(f"git --git-dir={fake} rev-parse main", tmp_path).stdout.strip()
    left = [l for l in sh("git status --porcelain", work).stdout.splitlines() if not l.startswith("??")]
    assert left == [], left[:10]                                                      # nothing "changed" any more
    assert version_of(work) == version_of(ROOT)                                        # files untouched


def test_publish_leaves_a_folder_with_its_own_commits_alone(tmp_path):
    fake, work, env = _project_with_git(tmp_path)
    sh("git -c user.email=t@t -c user.name=t commit -qm mine --allow-empty", work)
    mine = sh("git rev-parse HEAD", work).stdout.strip()
    r = sh("bash tools/publish_to_github.sh", work, **env)
    assert "own commits that aren't on GitHub" in r.stdout, r.stdout[-1200:] + r.stderr[-600:]
    assert sh("git rev-parse HEAD", work).stdout.strip() == mine
