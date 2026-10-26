"""What's new after an update."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from ginkassistant.services import whats_new as w

SAMPLE = """# Changelog

## 0.2.0 (November 2026)

- A future thing

## 0.1.3 (October 2026)

New abilities:
- A money book: "I sold rice",
  across two lines
- Invoices

## 0.1.2 (October 2026)

- Older fix
"""


def test_sections_and_since():
    assert w.sections(SAMPLE)[1] == ("0.1.3", ['A money book: "I sold rice", across two lines', "Invoices"])
    assert [v for v, _ in w.since(SAMPLE, "0.1.1", "0.1.3")] == ["0.1.3", "0.1.2"]          # never ahead of the app
    assert w.since(SAMPLE, "0.1.3", "0.1.3") == [] and [v for v, _ in w.since(SAMPLE, "", "0.1.3", limit=1)] == ["0.1.3"]
    assert [v for v, _ in w.since(SAMPLE, "0.1.2", "0.1.10")] == ["0.1.3"]                    # 0.1.10 > 0.1.3 (numbers, not text)


def test_the_app_ships_the_same_changelog():
    main = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    assert w.changelog_text() == main, "copy CHANGELOG.md to src/ginkassistant/resources/CHANGELOG.md"
    newest = w.sections(main)[0][0]
    import re
    assert newest == re.search(r'^version = "([^"]+)"', open(os.path.join(ROOT, "pyproject.toml")).read(), re.M).group(1)
