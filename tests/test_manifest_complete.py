"""tools/publish_to_github.sh publishes EXACTLY the files in tools/MANIFEST.txt: a new file missing from it never
reaches GitHub -- and Render, the app builds and the stores build from GitHub. Every file in a published folder
must be listed (0.1.154: the face model files and Lock Gink's device check were nearly left behind)."""
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
FOLDERS = ("src", "tests", "webapp", "cli", "sdk", "deploy", "tools", "website", "icons", ".github")
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".git", "_site", "out"}
OWNER_DATA = ("tools/gink_dataset/paraphrases.csv", "tools/gink_dataset/translations.csv",
              "tools/gink_dataset/examples_general.csv", "tools/gink_dataset/languages")    # the owner's own (publish_to_github.sh)


def test_every_published_file_is_in_the_manifest():
    listed = set(open(os.path.join(ROOT, "tools", "MANIFEST.txt"), encoding="utf-8").read().split())
    missing = []
    for top in FOLDERS:
        for folder, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".dist-info")]
            for name in files:
                if name.endswith(".pyc") or name == ".DS_Store":
                    continue
                rel = os.path.relpath(os.path.join(folder, name), ROOT).replace(os.sep, "/")
                if rel not in listed and not rel.startswith(OWNER_DATA) and not rel.startswith(".github/ISSUE_TEMPLATE"):
                    missing.append(rel)
    assert missing == [], "add to tools/MANIFEST.txt: " + ", ".join(sorted(missing)[:20])


def test_everything_listed_exists():
    listed = [x for x in open(os.path.join(ROOT, "tools", "MANIFEST.txt"), encoding="utf-8").read().split() if x]
    assert [x for x in listed if not os.path.exists(os.path.join(ROOT, x))] == []


def test_gitignore_lets_published_binaries_through(tmp_path):
    """.gitignore drops *.bin and models/ (big AI downloads) -- but People's face model must reach GitHub."""
    import shutil
    import subprocess
    if not shutil.which("git"):
        import pytest
        pytest.skip("needs git")
    shutil.copy(os.path.join(ROOT, ".gitignore"), tmp_path / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    listed = [x for x in open(os.path.join(ROOT, "tools", "MANIFEST.txt"), encoding="utf-8").read().split() if x]
    ignored = [x for x in listed if subprocess.run(["git", "check-ignore", "-q", x], cwd=tmp_path).returncode == 0]
    assert ignored == [], ignored
