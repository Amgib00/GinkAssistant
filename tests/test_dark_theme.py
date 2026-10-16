"""Dark theme regressions: the whole window goes dark, and switches show on/off."""
import os, re, subprocess, sys, json, shutil
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


def _page():
    from ginkassistant.ui import web_chat_view as w
    return w._build_page_html("Hi", "")


def test_dark_colours_cover_the_html_element():
    h = _page()
    assert "html.theme-dark, body.theme-dark {" in h                  # <html> paints below short chats
    assert "document.documentElement.classList.toggle('theme-dark'" in h
    i = h.index("  html, body {"); assert "min-height: 100%" in h[i:h.index("}", i)]


def test_switches_stay_blue_when_on_in_dark_mode():
    h = _page()
    off = h.index("body.theme-dark .sw i { background: #4A524C; }")
    on = h.index("body.theme-dark .sw input:checked + i { background: #2F7DE1; }")
    assert on > off                                                   # equal weight -> the later rule must be "on"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_page_javascript_parses(tmp_path):
    scripts = re.findall(r"<script>(.*?)</script>", _page(), re.S)
    f = tmp_path / "page.js"; f.write_text("\n;\n".join(scripts))
    assert subprocess.run(["node", "--check", str(f)], capture_output=True).returncode == 0
