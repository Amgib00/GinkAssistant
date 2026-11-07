"""Gink's own fine-tuned model (tools/gink_model) served from any OpenAI-style provider: off until set
up, only for testers while testing, never silently replaced by another model."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx
import pytest


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "own.db"))
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    for k in ("GINK_OWN_BASE", "GINK_OWN_KEY", "GINK_OWN_MODEL", "GINK_OWN_NAME", "GINK_OWN_TESTERS"):
        monkeypatch.delenv(k, raising=False)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    calls = []
    real = httpx.AsyncClient

    class Upstream:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            calls.append({"url": url, "body": json, "auth": (headers or {}).get("Authorization")})
            status = 503 if "own.example" in url and json.get("model") == "down" else 200
            return httpx.Response(status, json={"choices": [{"message": {"role": "assistant", "content": "Hi from upstream"}}]}
                                  if status == 200 else {"error": {"message": "down"}})
        async def get(self, url, headers=None):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b", "object": "model"}]})
    monkeypatch.setattr(httpx, "AsyncClient", Upstream)
    async def same(model, images=False): return model
    monkeypatch.setattr(b, "_current_model", same)
    b._models_cache.update(at=0, data=None)
    c = TestClient(b.app)

    def token(email):
        b._upsert_user(email, "T", None, "password")
        return {"Authorization": "Bearer " + b._token_response(email, "T")["token"]}
    yield b, c, token, calls, monkeypatch
    monkeypatch.setattr(httpx, "AsyncClient", real)


def setup_own(mp, testers=""):
    mp.setenv("GINK_OWN_BASE", "https://own.example/v1/"); mp.setenv("GINK_OWN_KEY", "own-key")
    mp.setenv("GINK_OWN_MODEL", "accounts/ibrahim/models/gink-qwen35-9b-lora")
    if testers:
        mp.setenv("GINK_OWN_TESTERS", testers)


def chat(c, h, model, text="Set an alarm for 6:30"):
    return c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": model, "messages": [{"role": "user", "content": text}]})


def test_off_until_set_up(srv):
    b, c, token, calls, mp = srv
    h = token("ib@x.co")
    assert chat(c, h, "gink-1").status_code in (200, 400, 404, 502) and not any("own.example" in x["url"] for x in calls)
    assert "gink-1" not in [m["id"] for m in c.get("/ai/openai/v1/models", headers=h).json()["data"]]


def test_routes_to_its_provider(srv):
    b, c, token, calls, mp = srv
    setup_own(mp)
    h = token("ib@x.co")
    r = chat(c, h, "gink-1", "What's the weather in Dakar right now?")                  # would auto-search otherwise
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "Hi from upstream"
    last = calls[-1]
    assert last["url"] == "https://own.example/v1/chat/completions" and last["auth"] == "Bearer own-key"
    assert last["body"]["model"] == "accounts/ibrahim/models/gink-qwen35-9b-lora"
    assert "user" not in last["body"] and "reasoning_effort" not in last["body"]          # no email hash leaves for it
    assert "gink-1" in [m["id"] for m in c.get("/ai/openai/v1/models", headers=h).json()["data"]]
    chat(c, h, "gink-crystal")
    assert "groq" in calls[-1]["url"]                                                     # other models unchanged


def test_testers_only_while_testing(srv):
    b, c, token, calls, mp = srv
    setup_own(mp, testers="Ib@x.co, owner@x.co")
    me, other = token("ib@x.co"), token("someone@x.co")
    assert chat(c, me, "gink-1").status_code == 200
    r = chat(c, other, "gink-1")
    assert r.status_code == 403 and r.json()["error"]["code"] == "model_not_available"
    assert "gink-1" not in [m["id"] for m in c.get("/ai/openai/v1/models", headers=other).json()["data"]]
    assert "gink-1" in [m["id"] for m in c.get("/ai/openai/v1/models", headers=me).json()["data"]]


def test_never_silently_replaced(srv):
    b, c, token, calls, mp = srv
    setup_own(mp)
    mp.setenv("GINK_OWN_MODEL", "down")
    r = chat(c, token("ib@x.co"), "gink-1")
    assert r.status_code == 503 and all("groq" not in x["url"] for x in calls)            # an honest error, no swap


def test_custom_name_and_teen_safety_still_apply(srv):
    b, c, token, calls, mp = srv
    setup_own(mp)
    mp.setenv("GINK_OWN_NAME", "Gink-Baobab")
    import time
    h = token("teen@x.co")
    b._set_birth_year("teen@x.co", time.gmtime().tm_year - 15)
    assert chat(c, h, "gink-baobab").status_code == 200
    assert calls[-1]["body"]["messages"][0]["content"] == b.TEEN_SAFETY                    # every model, every provider
