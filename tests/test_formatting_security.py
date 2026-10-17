"""SECURITY: text shown in Gink's window (AI answers, web content, synced chats) must not run code."""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ginkassistant.services.markdown_render import render_markdown_body as render


def test_raw_html_is_shown_as_text():
    for bad in ("<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "<iframe src=//evil.example>",
                '<a href="#" onclick="ginkEmit(\'settings_action\', {name: \'delete_account\'})">x</a>',
                "<div>\n<script>alert(1)</script>\n</div>"):
        out = render("hi " + bad)
        tags = re.findall(r"<[a-zA-Z][^>]*>", out)              # real tags only (escaped text is harmless)
        assert not any(re.match(r"<(script|img|iframe|a)\b", t) for t in tags), out
        assert not any(re.search(r"\son[a-z]+\s*=", t) for t in tags), out


def test_dangerous_link_targets_are_neutralised():
    for t in ("[a](javascript:alert(1))", "[a](JaVaScRiPt:alert(1))", "[a](java\tscript:alert(1))",
              "[a](data:text/html,x)", "[a](vbscript:x)", "![i](javascript:alert(1))", "[a]( javascript:alert(1))"):
        assert not re.search(r'(href|src)="\s*(java|vb|data:text)', render(t), re.I), t


def test_normal_formatting_still_works():
    out = render("**bold** [site](https://example.com) [f](gink://file/A.pdf) `x < y`\n\n```python\nprint('<b>')\n```")
    assert "<strong>bold</strong>" in out and 'href="https://example.com"' in out and "gink://file/A.pdf" in out
    assert "x &lt; y" in out and "code-block" in out


def test_narrow_spaces_show_as_normal_spaces():
    """GPT-OSS writes '2:23\\u202fPM' / 'Saturday,\\u202fOctober' -- narrow spaces made words look glued."""
    out = render("It\u2019s **2:23\u202fPM** on **Saturday,\u202fOctober\u2009\u202f17**")
    assert "2:23 PM" in out and "Saturday, October" in out and "\u202f" not in out and "\u2009" not in out
