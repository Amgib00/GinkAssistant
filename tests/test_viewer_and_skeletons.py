"""The in-app viewer always shows its close button; skeletons while things load."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("TOGA_BACKEND", "toga_dummy")


def test_viewer_close_button_first_short_title_and_skeleton():
    import toga
    from ginkassistant.ui.viewer import Viewer
    app = toga.App("t", "org.t") if not toga.App.app else toga.App.app
    v = Viewer(app, toga.Box())
    if not v.mobile:
        assert v.view.children[0].children[0] is v.close_btn            # a long title can't push it away
    assert v.short_title("https://www.youtube.com/results?search_query=Floating+Genom") == "YouTube"
    assert v.short_title("https://example.org/x", "A" * 80).endswith("\u2026") and len(v.short_title("https://e.org", "A" * 80)) == 40
    v.show("https://www.youtube.com/watch?v=abc")
    assert v.skeleton.style.display == "pack" and v.web.style.flex == 0     # skeleton while loading
    v._loaded()
    assert v.skeleton.style.display == "none" and v.web.style.flex == 1


def test_settings_lists_show_skeleton_rows_while_loading():
    page = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "settings_page.py"), encoding="utf-8").read()
    assert "if (!r.items.length && /^Loading/.test(r.empty || ''))" in page and "@keyframes sk-shine" in page
    assert "@media (prefers-reduced-motion: reduce) { .sk { animation: none; } }" in page


def test_requirement_files_agree_on_numpy():
    """Installing both files together failed: requirements-test.txt said numpy<2.0, requirements.txt numpy 2.2."""
    import re
    def numpy_lines(name):
        text = open(os.path.join(ROOT, name), encoding="utf-8").read()
        return {re.sub(r"\s+#.*", "", l).split(";")[0].replace(" ", "") for l in text.splitlines()
                if l.strip().startswith("numpy") and 'python_version>="3.13"' not in l.replace(" ", "")}
    main, test = numpy_lines("requirements.txt"), numpy_lines("requirements-test.txt")
    assert test <= main or not test, f"numpy rules differ: requirements.txt {main} vs requirements-test.txt {test}"


def test_intel_macs_can_install_everything():
    """webauthn 3.x needs cryptography 49+, which has no Intel-Mac builds (Gink allows <49 there):
    pip searched back to a 2019 cryptography and failed. Intel Macs get webauthn 2.7+ (tested)."""
    from packaging.requirements import Requirement
    intel_mac = {"sys_platform": "darwin", "platform_machine": "x86_64", "python_version": "3.10",
                 "platform_system": "Darwin", "platform_release": "19.6.0"}
    rules = {}
    for name in ("requirements.txt", "requirements-test.txt"):
        for line in open(os.path.join(ROOT, name), encoding="utf-8"):
            line = line.split(" #")[0].strip()
            if not line or line.startswith(("#", "-")):
                continue
            r = Requirement(line)
            if r.marker is None or r.marker.evaluate(intel_mac):
                rules.setdefault(r.name.lower(), []).append(r.specifier)
    crypto_ok = [v for v in ("48.0.1",) if all(v in s for s in rules["cryptography"])]
    assert crypto_ok, rules["cryptography"]
    assert all("3.0.1" not in s for s in rules["webauthn"]), "Intel Macs must not get webauthn 3.x"
    assert all("2.7.0" in s for s in rules["webauthn"])
    assert all("5.7.1" in s and "6.1.5" not in s for s in rules["cbor2"]), "cbor2 6.x must be built with Rust on Intel Macs"


def test_unfinished_batches_resume_when_the_server_starts(tmp_path, monkeypatch):
    """Startup work moved from @app.on_event (being removed from FastAPI) to a lifespan function."""
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "b.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    rows = [("b-running",), ("b-queued",)]
    monkeypatch.setattr(b, "_dev_db", lambda fn: rows)
    started = []
    monkeypatch.setattr(b, "_start_batch", started.append)
    with TestClient(b.app):                      # entering runs the startup (lifespan)
        pass
    assert started == ["b-running", "b-queued"]
    assert not b.app.router.on_startup, "use the lifespan function, not @app.on_event"
