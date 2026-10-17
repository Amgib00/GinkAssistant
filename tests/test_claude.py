"""Claude (Anthropic) in Gink: Pro only, own daily allowance, falls back to Groq without a key,
current models only, never sends the Groq key to Anthropic (or the reverse)."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "c.db"))
    monkeypatch.setenv("GROQ_API_KEY", "groq-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    calls = []

    def handler(request):
        host = request.url.host
        if request.url.path.endswith("/models"):
            ids = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"] if "anthropic" in host else ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
            return httpx.Response(200, json={"data": [{"id": i} for i in ids]})
        calls.append({"provider": "anthropic" if "anthropic" in host else "groq", "auth": request.headers.get("authorization"),
                      "body": json.loads(request.content)})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real(transport=httpx.MockTransport(handler),
                                                                    **{x: y for x, y in k.items() if x != "transport"}))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._claude_models.update(ids=set(), at=0.0); b._groq_models.update(ids=set(), at=0.0); b._models_cache.update(data=None, at=0.0)
    monkeypatch.setattr(b, "_plan_status", lambda email: {"plan": "pro" if email.startswith("pro") else "free"})
    c = TestClient(b.app)
    h = lambda email: {"Authorization": "Bearer " + b._token_response(email, "U")["token"]}
    return b, c, h, calls


def ask(c, h, model, **extra):
    return c.post("/ai/openai/v1/chat/completions", headers={**h, **extra.pop("headers", {})},
                  json={"model": model, "messages": [{"role": "user", "content": "hi"}], **extra})


def test_pro_claude_goes_to_anthropic_with_the_anthropic_key(srv):
    b, c, h, calls = srv
    assert ask(c, h("pro@x.co"), "claude-sonnet-5-5").status_code == 200
    call = calls[-1]
    assert call["provider"] == "anthropic" and call["auth"] == "Bearer anthropic-secret"
    assert call["body"]["model"] == "claude-sonnet-5-5" and "user" not in call["body"] and "reasoning_effort" not in call["body"]


def test_groq_models_still_go_to_groq_with_the_groq_key(srv):
    b, c, h, calls = srv
    assert ask(c, h("pro@x.co"), "openai/gpt-oss-120b").status_code == 200
    assert calls[-1]["provider"] == "groq" and calls[-1]["auth"] == "Bearer groq-secret"


def test_claude_is_for_pro(srv):
    b, c, h, calls = srv
    r = ask(c, h("free@x.co"), "claude-sonnet-5-5")
    assert r.status_code == 403 and r.json()["error"]["code"] == "pro_required" and not calls


def test_without_an_anthropic_key_groq_answers_instead(srv, monkeypatch):
    b, c, h, calls = srv
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert ask(c, h("free@x.co"), "claude-opus-5-5").status_code == 200
    assert calls[-1]["provider"] == "groq" and calls[-1]["body"]["model"] == "openai/gpt-oss-120b"


def test_old_or_unknown_claude_models_get_a_current_one(srv):
    b, c, h, calls = srv
    ask(c, h("pro@x.co"), "claude-3-opus-20240229")
    assert calls[-1]["body"]["model"] == "claude-sonnet-5-5"


def test_claude_daily_allowance_counts_questions_not_calls(srv, monkeypatch):
    b, c, h, calls = srv
    monkeypatch.setenv("GINK_PRO_CLAUDE_DAILY", "2")
    user = h("pro2@x.co")
    t1 = {"X-Gink-Turn": "turn-aaaaaaaaaaaa1"}
    assert [ask(c, user, "claude-sonnet-5-5", headers=t1).status_code for _ in range(3)] == [200, 200, 200]   # one question
    assert ask(c, user, "claude-sonnet-5-5", headers={"X-Gink-Turn": "turn-bbbbbbbbbbbb2"}).status_code == 200
    r = ask(c, user, "claude-sonnet-5-5", headers={"X-Gink-Turn": "turn-cccccccccccc3"})
    assert r.status_code == 429 and "Claude" in r.json()["error"]["message"]
    assert ask(c, user, "openai/gpt-oss-120b").status_code == 200                                         # Groq still works


def test_model_lists_include_claude_only_with_a_key(srv, monkeypatch):
    b, c, h, calls = srv
    ids = [m["id"] for m in c.get("/ai/openai/v1/models", headers=h("pro@x.co")).json()["data"]]
    assert "claude-sonnet-5-5" in ids and "openai/gpt-oss-120b" in ids
    monkeypatch.delenv("ANTHROPIC_API_KEY"); b._models_cache.update(data=None, at=0.0)
    ids = [m["id"] for m in c.get("/ai/openai/v1/models", headers=h("pro@x.co")).json()["data"]]
    assert not any(i.startswith("claude-") for i in ids)


def test_owner_can_grant_pro_and_nobody_else_can(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "g.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    b._upsert_user("me@x.co", "Me", provider="password")                     # a real sign-up creates the account
    grant = lambda key, **d: c.post("/admin/grant-pro", headers={"x-admin-key": key}, json={"email": "me@x.co", "days": 30, **d})
    monkeypatch.delenv("GINK_ADMIN_KEY", raising=False)
    assert grant("anything").status_code == 403                            # no admin key set: refused
    monkeypatch.setenv("GINK_ADMIN_KEY", "short")
    assert grant("short").status_code == 403                               # guessable key: refused
    monkeypatch.setenv("GINK_ADMIN_KEY", "k" * 40)
    assert grant("wrong" * 8).status_code == 403
    assert grant("k" * 40, email="nobody@x.co").status_code == 404
    assert grant("k" * 40, days=5000).status_code == 422
    assert b._plan_status("me@x.co")["plan"] == "free"
    r = grant("k" * 40)
    assert r.status_code == 200 and b._plan_status("me@x.co")["plan"] == "pro"
    first = r.json()["pro_until"]
    assert grant("k" * 40).json()["pro_until"] > first + 29 * 86400          # adds to the end, like a payment


def test_gink_names_reach_the_right_claude_model(srv):
    b, c, h, calls = srv
    for name, model in (("gink-flurry", "claude-haiku-5-5"), ("gink-frost", "claude-sonnet-5-5"), ("Gink-Glacier", "claude-opus-5-5")):
        assert ask(c, h("pro@x.co"), name).status_code == 200
        assert calls[-1]["provider"] == "anthropic" and calls[-1]["body"]["model"] == model
    assert ask(c, h("free@x.co"), "gink-frost").status_code == 403          # still Pro only


def test_gink_names_for_the_free_models_reach_groq(srv):
    b, c, h, calls = srv
    for name, model in (("gink-flake", "openai/gpt-oss-20b"), ("gink-crystal", "openai/gpt-oss-120b")):
        assert ask(c, h("free@x.co"), name).status_code == 200
        assert calls[-1]["provider"] == "groq" and calls[-1]["body"]["model"] == model
