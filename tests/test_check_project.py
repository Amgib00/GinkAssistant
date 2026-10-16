"""tools/check_project.py: finds and safely repairs the layout problems that put builds/icons in the wrong place."""
import os, shutil, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
ROOT = os.path.join(os.path.dirname(__file__), "..")


def make_messy_copy(tmp):
    proj = tmp / "GinkAssistant"
    proj.mkdir()
    shutil.copy(os.path.join(ROOT, "pyproject.toml"), proj / "pyproject.toml")
    (proj / "src" / "ginkassistant").mkdir(parents=True)
    # problem 1: an old build folder outside build/
    (proj / "macOS" / "Gink" / "Gink.app").mkdir(parents=True)
    # problem 2: the icons are in resources/, not icons/
    shutil.copytree(os.path.join(ROOT, "icons"), proj / "resources", ignore=shutil.ignore_patterns("source-icon.png"))
    # problem 3: an old setting Briefcase ignores
    s = (proj / "pyproject.toml").read_text().replace('[tool.briefcase.app.ginkassistant.macOS]\n',
                                                      '[tool.briefcase.app.ginkassistant.macOS]\noutput_dir = "macos"\n', 1)
    (proj / "pyproject.toml").write_text(s)
    # problem 4: a built app without an icon inside
    (proj / "build" / "ginkassistant" / "macos" / "app" / "Gink.app" / "Contents" / "Resources").mkdir(parents=True)
    return proj


def test_reports_then_fixes(tmp_path, monkeypatch):
    import check_project as cp
    proj = make_messy_copy(tmp_path)
    monkeypatch.chdir(proj)
    lines = []
    problems, fixed = cp.check(str(proj), fix=False, out=lines.append, briefcase_check=False)
    text = "\n".join(lines)
    assert problems == 4 and fixed == 0
    assert "output_dir" in text and "./macOS/" in text and "found in resources/" in text and "no icon in Contents/Resources" in text
    assert (proj / "macOS").is_dir() and not (proj / "icons").exists()          # report mode changes nothing

    lines.clear()
    problems, fixed = cp.check(str(proj), fix=True, out=lines.append, briefcase_check=False)
    assert fixed == 2                                                            # leftover moved + icons copied
    assert not (proj / "macOS").exists()
    backups = list((proj / "_old_builds").iterdir())
    assert (backups[0] / "macOS" / "Gink" / "Gink.app").is_dir()                # moved, never deleted
    assert (proj / "icons" / "ginkassistant.icns").is_file() and (proj / "icons" / "ginkassistant-adaptive-432.png").is_file()

    lines.clear()
    problems, _ = cp.check(str(proj), fix=False, out=lines.append, briefcase_check=False)
    text = "\n".join(lines)
    assert f"all {len(cp.ICON_SUFFIXES)} icon files present" in text and "./macOS/" not in text
    assert problems == 2       # what --fix can't do for you: remove output_dir + re-copy the icon into the built app


def test_real_project_is_clean():
    import check_project as cp
    lines = []
    cwd = os.getcwd(); os.chdir(ROOT)
    try:
        problems, _ = cp.check(os.path.abspath(ROOT), fix=False, out=lines.append, briefcase_check=False)
    finally:
        os.chdir(cwd)
    assert problems == 0, "\n".join(lines)


def test_one_folder_counted_once_when_names_ignore_case(tmp_path, monkeypatch):
    """On a Mac disk ./macOS, ./macos and ./MacOS are the same folder -- report and move it once."""
    import check_project as cp
    proj = make_messy_copy(tmp_path)
    (proj / "macos").symlink_to(proj / "macOS", target_is_directory=True)     # same folder, other spelling
    (proj / "MacOS").symlink_to(proj / "macOS", target_is_directory=True)
    lines = []
    cp.check(str(proj), fix=False, out=lines.append, briefcase_check=False)
    stray = [l for l in lines if "leftover build folder" in l]
    assert len(stray) == 1 and "./macOS/" in stray[0]                          # once, with its real name



def _fake_env(monkeypatch, cp, env_version, cmd_path, cmd_version):
    import importlib.metadata as md, subprocess
    monkeypatch.setattr(md, "version", lambda name: env_version if env_version else (_ for _ in ()).throw(md.PackageNotFoundError()))
    monkeypatch.setattr(cp.shutil, "which", lambda name: cmd_path)
    class R: stdout = cmd_version
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())


def test_old_briefcase_is_spotted(monkeypatch):
    import check_project as cp
    _fake_env(monkeypatch, cp, "0.3.12", os.path.join(os.path.dirname(sys.executable), "briefcase"), "0.3.12")
    lines = []
    assert cp.check_briefcase(lines.append) == 1
    assert "too old" in lines[0] and "./macOS/" in lines[0] and "briefcase" in lines[1]


def test_briefcase_from_another_place_is_spotted(monkeypatch):
    import check_project as cp
    _fake_env(monkeypatch, cp, "0.4.4", "/usr/local/bin/briefcase", "0.3.10")
    lines = []
    assert cp.check_briefcase(lines.append) == 1
    assert any("NOT the one in this environment" in l and "0.3.10" in l for l in lines)
    assert any("python -m briefcase" in l for l in lines)


def test_current_briefcase_passes(monkeypatch):
    import check_project as cp
    _fake_env(monkeypatch, cp, "0.4.4", os.path.join(os.path.dirname(sys.executable), "briefcase"), "0.4.4")
    lines = []
    assert cp.check_briefcase(lines.append) == 0 and "Briefcase 0.4.4" in lines[0]


def test_leftover_folder_says_old_briefcase_built_it(tmp_path, monkeypatch):
    import check_project as cp
    proj = make_messy_copy(tmp_path)
    lines = []
    cp.check(str(proj), fix=False, out=lines.append, briefcase_check=False)
    assert any("./macOS/" in l and "built by Briefcase 0.3.12 or older" in l for l in lines)



def test_catalina_needs_briefcase_0315(monkeypatch):
    """On macOS 10.15, 0.4.x builds apps that need macOS 11 (error -10825) -- recommend 0.3.15."""
    import check_project as cp
    monkeypatch.setattr(cp, "_old_mac", lambda: "10.15.7")
    _fake_env(monkeypatch, cp, "0.4.4", os.path.join(os.path.dirname(sys.executable), "briefcase"), "0.4.4")
    lines = []
    assert cp.check_briefcase(lines.append) == 1
    assert "won't open on this Mac" in lines[0] and "0.3.15" in lines[0] and 'briefcase==0.3.15' in lines[1]
    _fake_env(monkeypatch, cp, "0.3.15", os.path.join(os.path.dirname(sys.executable), "briefcase"), "0.3.15")
    lines = []
    assert cp.check_briefcase(lines.append) == 0 and "apps open on this Mac" in lines[0]
    _fake_env(monkeypatch, cp, "0.3.12", os.path.join(os.path.dirname(sys.executable), "briefcase"), "0.3.12")
    lines = []
    assert cp.check_briefcase(lines.append) == 1 and "./macOS/" in lines[0] and "0.3.15" in lines[1]


def test_newer_macs_keep_04x(monkeypatch):
    import check_project as cp
    monkeypatch.setattr(cp, "_old_mac", lambda: "")
    _fake_env(monkeypatch, cp, "0.4.4", os.path.join(os.path.dirname(sys.executable), "briefcase"), "0.4.4")
    lines = []
    assert cp.check_briefcase(lines.append) == 0
