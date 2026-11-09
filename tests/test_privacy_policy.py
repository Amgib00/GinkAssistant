"""The privacy policy describes what Gink really does: when a feature that touches personal data lands, its
paragraph belongs in website/pages/privacy.html (this list grows with them)."""
import os
ROOT = os.path.join(os.path.dirname(__file__), "..")

MUST_MENTION = {
    "error reports (0.1.111)": "Send error reports",
    "training opt-in (0.1.109)": "Help improve Gink",
    "workspaces + healthcare mode (0.1.113)": "healthcare mode",
    "parental controls (0.1.96)": "never the words",
    "time zone / region (0.1.126)": "time zone and language setting",
    "photo to image (0.1.114)": "Use a photo",
    "email results (0.1.135)": "agent results you asked to receive by email",
    "webhooks (0.1.133)": "webhook",
    "server export (0.1.137)": "Download everything on the server",
    "deletion sweep (0.1.138)": "everything else that names your account",
    "phone sign-in (0.1.95)": "sign in with your phone number",
    "agents and schedules (0.1.121, 0.1.132)": "scheduled tasks",
}


def test_policy_covers_every_feature():
    text = open(os.path.join(ROOT, "website", "pages", "privacy.html"), encoding="utf-8").read()
    missing = [k for k, phrase in MUST_MENTION.items() if phrase not in text]
    assert missing == [], missing
    assert "Last updated" in text


TERMS_MUST_MENTION = {
    "not medical advice (healthcare mode)": "not a medical device",
    "workspace responsibility": "admins, are responsible",
    "API keys secret": "Keep your API keys secret",
    "agents and webhooks": "webhooks run until you pause or delete them",
    "fair use": "Fair-use limits apply",
    "training opt-in": "Help improve Gink",
}


def test_terms_cover_the_developer_platform_and_workspaces():
    text = open(os.path.join(ROOT, "website", "pages", "terms.html"), encoding="utf-8").read()
    missing = [k for k, phrase in TERMS_MUST_MENTION.items() if phrase not in text]
    assert missing == [], missing


def test_the_apps_tell_people_once_when_the_policies_change(tmp_path, monkeypatch):
    """The privacy policy and terms promise an in-app notice for important changes: /info says when they last
    changed; the apps, web app, Genie and console show a notice until the person says OK (once per change)."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "src"))
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "p.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    info = TestClient(b.app).get("/info").json()
    assert info["policies_updated"] == b.POLICIES_UPDATED and info["privacy_url"].endswith("privacy.html")
    assert info["terms_url"].endswith("terms.html")
    page = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "web_chat_view.py"), encoding="utf-8").read()
    main = open(os.path.join(ROOT, "src", "ginkassistant", "ui", "main_screen.py"), encoding="utf-8").read()
    bridge = open(os.path.join(ROOT, "webapp", "bridge.js"), encoding="utf-8").read()
    assert "function policyNotice(" in page and "policy_seen" in main and "checkPolicies();" in bridge
    for f in ("genie.html", "console.html"):
        assert "gink_policy_seen" in open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", f), encoding="utf-8").read(), f
    privacy = open(os.path.join(ROOT, "website", "pages", "privacy.html"), encoding="utf-8").read()
    import datetime
    d = datetime.date.fromisoformat(b.POLICIES_UPDATED)
    assert f"Last updated {d.day} {d:%B %Y}" in privacy                              # the date matches the page
