"""Long chats fit the AI model's limits (0.1.163). A chat that made a web page three times sent all three copies:
Groq refused it ("Request too large ... Limit 8000, Requested 17295") and its raw message -- with the organization id
of Gink's Groq account -- reached the person. Now earlier versions of an artifact are left out, the request is fitted
to the model (or goes to one that takes more), a refusal is asked again smaller, and people get plain words."""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx

ORG = "org_01exampleexampleexample00"
TOO_LARGE = ("Request too large for model `{m}` in organization `" + ORG + "` service tier `on_demand` on tokens per minute "
             "(TPM): Limit {limit}, Requested {asked}, please reduce your message size and try again. Need more tokens? "
             "Upgrade to Dev Tier today at https://console.groq.com/settings/billing")
BUSY = ("Rate limit reached for model `{m}` in organization `" + ORG + "` service tier `on_demand` on tokens per minute (TPM): "
        "Limit {limit}, Used 6524, Requested 3000. Please try again in 44.8575s. Need more tokens? Upgrade to Dev Tier today "
        "at https://console.groq.com/settings/billing")
SCOUT = "meta-llama/llama-4-scout-17b-16e-instruct"
IDS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile", SCOUT]


def page(n):
    return ("<!doctype html><html><head><title>Portfolio</title><style>" + "body{margin:0;font-family:system-ui}\n" * (40 * n)
            + "</style></head><body>" + "<section><h2>Work</h2><p>Projects I built in Freetown, Accra and Lyon.</p></section>\n"
            * (30 * n) + "</body></html>")


def portfolio_chat(last="My answers:\n• What would you like to add next? → Awards / Certifications section"):
    return [{"role": "system", "content": "You are Gink, a warm assistant. " * 300},
            {"role": "user", "content": "make me anything"},
            {"role": "assistant", "content": "A portfolio page:\n\n```html title=\"Personal Portfolio\"\n" + page(1) + "\n```"},
            {"role": "user", "content": "add more to it"},
            {"role": "assistant", "content": "With skills:\n\n```html title=\"Personal Portfolio\"\n" + page(2) + "\n```"},
            {"role": "user", "content": "continue"},
            {"role": "assistant", "content": "Fuller:\n\n```html title=\"Personal Portfolio\"\n" + page(3) + "\n```\n\nAnything else?"},
            {"role": "user", "content": last}]


# ---------------------------------------------------------------- the module
def test_earlier_versions_are_left_out_and_the_newest_stays():
    from ginkassistant.services import context_fit as cf
    msgs = portfolio_chat()
    out, n = cf.drop_old_versions(msgs)
    assert n == 2 and out[6] is msgs[6] and page(3) in out[6]["content"]                       # the newest, untouched
    assert page(1) not in out[2]["content"] and "“Personal Portfolio” was here" in out[2]["content"]
    assert out[2]["content"].startswith("A portfolio page:") and cf.estimate(out) < cf.estimate(msgs) * 0.75
    assert msgs[2]["content"].count(page(1)) == 1                                              # the original isn't changed
    # fences: ~~~ too, an unclosed block runs to the end, a title in curly quotes
    b = cf.blocks("x\n~~~python title=“invoice.py”\nprint(1)\n~~~\ny\n```css\nbody{}")
    assert [(x["lang"], x["title"], x["body"]) for x in b] == [("python", "invoice.py", "print(1)"), ("css", "", "body{}")]


def test_fitting_keeps_the_newest_artifact_and_the_last_turns_first():
    from ginkassistant.services import context_fit as cf
    msgs = portfolio_chat()
    assert cf.fit(msgs, 30000, 6144)[1] == 6144                                                 # fits: all the room
    small = cf.fit(msgs[:1] + msgs[-3:], 8000, 6144, min_answer=1024)
    assert small and small[1] < 6144 and "less room for the answer" in small[2]                  # less room, nothing lost
    gentle = cf.fit(msgs, 12000, 6144, min_answer=4000, level=1)                               # older turns go, the page stays
    assert gentle and page(3) in gentle[0][-2]["content"] and "older turns left out" in gentle[2] and gentle[1] >= 4000
    assert cf.fit(msgs, 8000, 6144, min_answer=4000, level=1) is None                           # never the newest page at level 1
    deep = cf.fit(msgs, 8000, 6144, min_answer=4000, level=2)
    assert deep and deep[0][-1] == msgs[-1] and cf.estimate(deep[0]) + deep[1] <= 8000 * cf.MARGIN
    # tool calls keep their results: a turn is left out whole
    turn = [{"role": "user", "content": "check my camera " + "x" * 9000},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "device_check", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "ok " * 3000}, {"role": "assistant", "content": "Done."}]
    fitted = cf.fit([msgs[0]] + turn + [{"role": "user", "content": "thanks"}, {"role": "assistant", "content": "You're welcome."},
                                       {"role": "user", "content": "and the microphone?"}], 8000, 1024)
    roles = [m["role"] for m in fitted[0]]
    assert "tool" not in roles and roles == ["system", "user", "assistant", "user"]


def test_groq_refusals_are_read_scrubbed_and_said_plainly():
    from ginkassistant.services import context_fit as cf
    big = TOO_LARGE.format(m="openai/gpt-oss-120b", limit=8000, asked=17295)
    assert cf.read_refusal(big) == {"kind": "TPM", "limit": 8000, "used": None, "requested": 17295, "wait": None}
    clean = cf.scrub(big)
    assert ORG not in clean and "organization" not in clean and "on_demand" not in clean and "Upgrade" not in clean
    assert "Limit 8000, Requested 17295" in clean
    words, code = cf.friendly_refusal(413, big)
    assert code == "too_large" and "too long" in words and "org_" not in words
    words, code = cf.friendly_refusal(429, BUSY.format(m="openai/gpt-oss-120b", limit=8000))
    assert code == "busy" and words.endswith("try again in 45 seconds.")
    assert cf.read_refusal("on tokens per day (TPD): Limit 200000, Used 199000, Requested 3000. Please try again in 7m12.5s.")["wait"] == 432.5
    assert cf.friendly_refusal(400, '{"error": {"message": "Please reduce the length of the messages"}}')[1] == "too_large"
    assert cf.seconds("523ms") == 0.523 and cf.seconds("1h2m3s") == 3723 and cf.wait_words(432) == "7 minutes"


# ---------------------------------------------------------------- the server
def server(monkeypatch, tmp_path, limits, busy=(), plan="pro", counts=True):
    """A pretend Groq that counts like Groq: a request's words and its max_tokens together, against each model's limit."""
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "s.db")); monkeypatch.setenv("GROQ_API_KEY", "g")
    sent = []

    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": i} for i in IDS]})
        body = json.loads(request.content)
        sent.append(body)
        m = body["model"]
        asked = int(len(json.dumps(body["messages"])) / 3.0) + (int(body.get("max_tokens") or 0) if counts else 0)
        if m in busy:
            return httpx.Response(429, json={"error": {"message": BUSY.format(m=m, limit=limits[m]), "type": "tokens", "code": "rate_limit_exceeded"}})
        if asked > limits.get(m, 6000):
            return httpx.Response(413, json={"error": {"message": TOO_LARGE.format(m=m, limit=limits.get(m, 6000), asked=asked),
                                                       "type": "tokens", "code": "rate_limit_exceeded"}})
        head = {"x-ratelimit-limit-tokens": str(limits.get(m, 6000)), "x-ratelimit-remaining-tokens": str(limits.get(m, 6000)),
                "x-ratelimit-reset-tokens": "7.5s"}
        if body.get("stream"):
            text = "".join("data: " + json.dumps(e) + "\n\n" for e in (
                {"choices": [{"index": 0, "delta": {"content": f"Added it ({m})."}}]},)) + "data: [DONE]\n\n"
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream", **head})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": f"ok ({m})"}}]}, headers=head)
    real = httpx.AsyncClient

    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0)
    b._tpm.clear()
    monkeypatch.setattr(b, "_plan_status", lambda e: {"plan": plan})
    monkeypatch.setattr(b, "_needs_search", lambda t: False)
    c = TestClient(b.app)
    h = {"Authorization": "Bearer " + b._token_response("ib@example.com", "I")["token"]}
    return b, c, h, sent


def said(r):
    return "".join(json.loads(l[6:])["choices"][0]["delta"].get("content", "") for l in r.text.splitlines()
                   if l.startswith("data: {") and json.loads(l[6:]).get("choices"))


def test_a_long_artifact_chat_goes_to_a_model_that_takes_it(tmp_path, monkeypatch):
    limits = {"openai/gpt-oss-120b": 8000, "openai/gpt-oss-20b": 8000, "qwen/qwen3.8-27b": 6000,
              "llama-3.3-70b-versatile": 12000, SCOUT: 30000}
    b, c, h, sent = server(monkeypatch, tmp_path, limits)
    b._tpm_counts["v"] = True                              # known already: the room for the answer counts
    r = c.post("/ai/openai/v1/chat/completions", headers=h,
               json={"model": "openai/gpt-oss-120b", "stream": True, "messages": portfolio_chat()})
    assert r.status_code == 200 and said(r) == f"Added it ({SCOUT})."
    assert sent[0]["model"] == SCOUT and len(sent) == 1                       # straight to the model that takes it
    text = json.dumps(sent[0]["messages"])
    assert text.count("<!doctype html>") == 1 and json.dumps(page(3))[1:-1] in text   # the newest page, once
    assert sent[0]["max_tokens"] == b.MAKE_TOKENS["pro"]                     # "My answers:" on an artifact: room to make it
    assert b._tpm[SCOUT]["limit"] == 30000 and b._health["fitted"] >= 1
    b._groq_models.update(ids=set(), at=0.0)
    b._tpm_counts["v"] = None


def test_a_refusal_is_asked_again_smaller_and_learned(tmp_path, monkeypatch):
    # Groq says the limit is 5000 (less than Gink assumed): asked again smaller, on the same model; then known
    limits = {"openai/gpt-oss-120b": 5000, "openai/gpt-oss-20b": 5000, "qwen/qwen3.8-27b": 4000,
              "llama-3.3-70b-versatile": 4000, SCOUT: 4000}
    b, c, h, sent = server(monkeypatch, tmp_path, limits, plan="free")
    chat = [{"role": "system", "content": "You are Gink."}] + [
        {"role": r, "content": f"{r} message {i}: " + "words " * 400} for i, r in enumerate(["user", "assistant"] * 5)] + [
        {"role": "user", "content": "and what about Dakar?"}]
    r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "openai/gpt-oss-120b", "messages": chat})
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "ok (openai/gpt-oss-120b)"
    assert sent[0]["model"] == sent[-1]["model"] == "openai/gpt-oss-120b" and len(sent) == 2
    assert len(sent[-1]["messages"]) < len(sent[0]["messages"]) and sent[-1]["messages"][-1]["content"] == "and what about Dakar?"
    assert b._tpm["openai/gpt-oss-120b"]["limit"] == 5000 and b._tpm_counts["v"] is True
    sent.clear()
    r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "openai/gpt-oss-120b", "messages": chat})
    assert r.status_code == 200 and len(sent) == 1 and sent[0]["model"] == "openai/gpt-oss-120b"   # known now: fitted at once
    # this minute's tokens used up (Groq's x-ratelimit-remaining-tokens): straight to another model, no refusal first
    import time
    b._tpm["openai/gpt-oss-120b"].update(remaining=10, reset_at=time.time() + 40)
    sent.clear()
    r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "openai/gpt-oss-120b",
                                                                  "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200 and [s["model"] for s in sent] == ["openai/gpt-oss-20b"]
    b._groq_models.update(ids=set(), at=0.0)


def test_people_get_plain_words_and_developers_get_groq_s_message_without_gink_s_details(tmp_path, monkeypatch):
    limits = {m: 1500 for m in IDS}
    b, c, h, sent = server(monkeypatch, tmp_path, limits)
    r = c.post("/ai/openai/v1/chat/completions", headers=h,
               json={"model": "openai/gpt-oss-120b", "stream": True, "messages": portfolio_chat()})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large" and "too long" in r.json()["error"]["message"]
    assert ORG not in r.text and "Upgrade" not in r.text and "organization" not in r.text
    # a developer (API key): Groq's own error, scrubbed, with the way to let Gink fit it
    key = c.post("/account/api-keys", headers=h, json={"name": "test"}).json()["key"]
    r = c.post("/v1/chat/completions", headers={"Authorization": "Bearer " + key},
               json={"model": "openai/gpt-oss-120b", "messages": portfolio_chat()})
    assert r.status_code == 413 and "Limit 1500" in r.json()["error"]["message"] and '"gink_fit": true' in r.json()["error"]["message"]
    assert ORG not in r.text and "Upgrade to Dev Tier" not in r.text
    b._groq_models.update(ids=set(), at=0.0)


def test_busy_everywhere_says_when_to_try_again(tmp_path, monkeypatch):
    b, c, h, sent = server(monkeypatch, tmp_path, {m: 30000 for m in IDS}, busy=set(IDS))
    r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "openai/gpt-oss-120b",
                                                                 "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 429 and r.json()["error"]["code"] == "busy" and "45 seconds" in r.json()["error"]["message"]
    assert r.headers["retry-after"] == "45" and ORG not in r.text and len(sent) == 4            # tried other models first
    b._groq_models.update(ids=set(), at=0.0)


def test_what_groq_says_teaches_gink_the_limits(tmp_path, monkeypatch):
    b, c, h, sent = server(monkeypatch, tmp_path, {m: 250000 for m in IDS})
    r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "openai/gpt-oss-120b",
                                                                  "messages": [{"role": "user", "content": "hello"}]})
    assert r.status_code == 200 and b._tpm["openai/gpt-oss-120b"]["limit"] == 250000      # a paid plan: learned
    sent.clear()
    r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "openai/gpt-oss-120b", "messages": portfolio_chat()})
    assert r.status_code == 200 and sent[0]["model"] == "openai/gpt-oss-120b" and sent[0]["max_tokens"] == b.MAKE_TOKENS["pro"]
    assert json.dumps(sent[0]["messages"]).count("<!doctype html>") == 1            # earlier versions still never go along
    monkeypatch.setenv("GINK_TPM_LIMITS", '{"openai/gpt-oss-120b": 99000}')
    assert b._tpm_limit("openai/gpt-oss-120b") == 99000
    b._groq_models.update(ids=set(), at=0.0)


def test_a_short_follow_up_on_an_artifact_gets_room_to_make_it():
    from ginkassistant.services import backend_server as b
    msgs = portfolio_chat("continue")
    body = {"model": "openai/gpt-oss-120b", "max_tokens": 1024}
    assert b._abilities(body, "free", "continue", msgs) == "make" and body["max_tokens"] == b.MAKE_TOKENS["free"]
    body = {"model": "openai/gpt-oss-120b", "max_tokens": 1024}
    assert b._abilities(body, "free", "what's the capital of Senegal?", msgs) == "" and body["max_tokens"] == 1024
    assert b._abilities({"max_tokens": 1}, "free", "continue", [{"role": "assistant", "content": "Hello!"}]) == ""
    assert b._answer_floor({"messages": msgs}, "make") > 2048 and b._answer_floor({"messages": msgs}, "") == 1024


def test_whether_the_answer_s_room_counts_is_learned_from_groq_itself(tmp_path, monkeypatch):
    # a question that fits, asking for more room than the limit leaves: asked with all of it once -- the answer says
    chat = [{"role": "system", "content": "You are Gink."}, {"role": "user", "content": "Write a long story set in Dakar " + "please " * 300}]
    for counts in (False, True):
        b, c, h, sent = server(monkeypatch, tmp_path, {m: 8000 for m in IDS}, counts=counts)
        b._tpm_counts["v"] = None
        r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "openai/gpt-oss-120b", "messages": chat})
        full = sent[0]["max_tokens"]
        assert r.status_code == 200 and full == b.MAKE_TOKENS["pro"]                    # all of it, once
        assert b._tpm_counts["v"] is counts
        if counts:                                                                      # refused: asked with less
            assert len(sent) == 2 and sent[1]["max_tokens"] < full
        else:
            assert len(sent) == 1
        sent.clear()
        r = c.post("/ai/openai/v1/chat/completions", headers=h, json={"model": "openai/gpt-oss-120b", "messages": chat})
        assert r.status_code == 200 and len(sent) == 1                                  # known now: right at once
        assert (sent[0]["max_tokens"] < full) is counts
        monkeypatch.undo()
        b._groq_models.update(ids=set(), at=0.0)
    b._tpm_counts["v"] = None
    monkeypatch.setenv("GINK_TPM_COUNTS_ANSWER", "1")
    assert b._answer_counts() is True
