"""Webhooks: when an agent run ends, Gink POSTs a signed notification -- public https addresses only; the SDKs verify
the signature; schedules pass their webhook to every run."""
import json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
import pytest
from test_genie import SCRIPT, call      # the simulated AI (genie_srv: conftest.py)

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def api(genie_srv, monkeypatch):
    b, c, h = genie_srv
    b._upsert_user("ib@example.com", "Ibrahim", None, "password")
    key = b._create_api_key("ib@example.com", "w")["key"]
    sent = []
    async def post(url, body, headers):
        sent.append((url, body, headers)); return 200
    monkeypatch.setattr(b, "_webhook_post", post)
    monkeypatch.setattr(b, "_webhook_url_ok", lambda url: url if str(url).startswith("https://hooks.example.com/") else
                        (_ for _ in ()).throw(b.HTTPException(status_code=400, detail="webhook_url must be on the public internet.")))
    return b, c, {"Authorization": f"Bearer {key}"}, h, sent


def test_a_finished_run_is_posted_and_signed(api):
    b, c, k, session, sent = api
    from gink import verify_webhook
    SCRIPT[:] = [{"content": "", "tool_calls": [call("write_file", path="a.md", content="a")]}, {"content": "Done."}]
    it = c.post("/v1/interactions", headers=k, json={"input": "Write a.md", "webhook_url": "https://hooks.example.com/gink"}).json()
    assert it["status"] == "completed"
    for _ in range(50):
        if sent:
            break
        time.sleep(0.05)
    url, body, headers = sent[-1]
    assert url == "https://hooks.example.com/gink" and headers["Gink-Signature"].startswith("t=")
    secret = c.get("/v1/webhooks/secret", headers=k).json()["secret"]
    event = verify_webhook(body, headers["Gink-Signature"], secret)
    assert event["type"] == "interaction.completed" and event["data"]["id"] == it["id"] and "webhook_url" not in event["data"]
    with pytest.raises(Exception):
        verify_webhook(body + b" ", headers["Gink-Signature"], secret)            # changed body: refused
    new = c.post("/v1/webhooks/secret/rotate", headers=k).json()["secret"]
    assert new != secret and new.startswith("whsec_")


def test_only_public_https_addresses():
    from ginkassistant.services import backend_server as b
    for bad in ("http://example.com/hook", "https://127.0.0.1/x", "https://localhost/x", "https://10.0.0.5/x",
                "https://169.254.169.254/latest", "https://user:pw@example.com/x", "ftp://example.com"):
        with pytest.raises(b.HTTPException):
            b._webhook_url_ok(bad)


def test_bad_webhook_is_refused_up_front(api):
    b, c, k, session, sent = api
    r = c.post("/v1/interactions", headers=k, json={"input": "x", "webhook_url": "https://169.254.169.254/x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_webhook_url"


def test_schedules_pass_their_webhook_on(api):
    b, c, k, session, sent = api
    s = c.post("/v1/schedules", headers=k, json={"input": "Brief", "webhook_url": "https://hooks.example.com/brief"}).json()
    assert s["webhook_url"] == "https://hooks.example.com/brief"
    SCRIPT[:] = [{"content": "Brief done."}]
    r = c.post(f"/v1/schedules/{s['id']}/run", headers=k).json()
    for _ in range(80):
        if sent:
            break
        time.sleep(0.05)
    assert sent and sent[-1][0] == "https://hooks.example.com/brief"
    assert json.loads(sent[-1][1])["data"]["id"] == r["interaction_id"]


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")
def test_js_verify_matches_the_server(tmp_path):
    from ginkassistant.services import backend_server as b
    body = json.dumps({"type": "interaction.completed", "data": {"id": "int_1"}})
    ts = int(time.time())
    sig = b._webhook_sign("whsec_test", body.encode(), ts)
    script = tmp_path / "v.mjs"
    script.write_text('''
import { verifyWebhook } from "%s";
const ok = await verifyWebhook(%s, %s, "whsec_test");
let refused = false;
try { await verifyWebhook(%s, %s, "whsec_other"); } catch (e) { refused = e.code === "bad_signature"; }
console.log(JSON.stringify({ id: ok.data.id, refused }));
''' % (os.path.join(ROOT, "sdk", "js", "index.js").replace("\\\\", "/"), json.dumps(body), json.dumps(sig), json.dumps(body), json.dumps(sig)))
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"id": "int_1", "refused": True}


def test_console_and_cli_pieces():
    page = open(os.path.join(ROOT, "src", "ginkassistant", "services", "web_app", "console.html"), encoding="utf-8").read()
    cli = open(os.path.join(ROOT, "cli", "gink_cli", "main.py"), encoding="utf-8").read()
    assert 'id="sch-hook"' in page and '"/dev/webhooks/secret"' in page and "--webhook" in cli and '["webhook", "secret"]' in cli
