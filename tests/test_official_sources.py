"""The "Official" badge on sources: governments, international public bodies and the organisation's own
site -- not universities or news; and in the app only Gink's own marker earns it."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ginkassistant.services import backend_server as b


def test_what_counts_as_official():
    for url in ("https://www.gov.sn/actualites", "https://senegal.gouv.sn", "https://www.statehouse.gov.sl", "https://www.go.ke",
                "https://www.who.int/news", "https://www.un.org/en", "https://www.worldbank.org/en/country/senegal",
                "https://ec.europa.eu/info", "https://www.nasa.gov", "https://www.ontario.gc.ca", "https://www.bceao.int"):
        assert b._is_official(url), url
    for url in ("https://www.bbc.com/news", "https://www.mit.edu", "https://example.ac.uk", "https://www.lemonde.fr",
                "https://en.wikipedia.org/wiki/Senegal", "https://news.google.com"):
        assert not b._is_official(url), url


def test_the_organisations_own_site():
    assert b._is_official("https://www.wave.com/en/", "What are Wave's fees in Senegal?")
    assert b._is_official("https://www.orange.sn/offres", "Orange Money tarifs")
    assert not b._is_official("https://www.wave.com/en/", "best mobile money app")         # not what was asked about
    assert not b._is_official("https://www.news.com", "latest news")                       # too generic to be a name


def test_sources_list_marks_and_orders(monkeypatch):
    token = b._question.set("How much does Wave charge?")
    try:
        md = b._sources_md([{"url": "https://www.bbc.com/x", "title": "BBC"}, {"url": "https://www.wave.com/fees", "title": "Wave fees"},
                            {"url": "https://www.gouv.sn/y", "title": "Gouvernement"}])
    finally:
        b._question.reset(token)
    lines = md.strip().split("\n")[1:]
    assert lines[0].endswith("\u00b7 official") and lines[1].endswith("\u00b7 official") and "BBC" in lines[2]
    assert not lines[2].endswith("official")


def test_app_trusts_only_ginks_marker():
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "ginkassistant", "ui", "chat_extras.py"), encoding="utf-8").read()
    assert "official: /\\u00b7\\s*official\\s*$/i.test(after.trim())" in src
    assert "official: /official/i.test(after)" not in src
