"""The gink CLI (cli/), run as a real program against the real server (only Groq is simulated)."""
import builtins, json, os, stat, subprocess, sys, threading, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src")); sys.path.insert(0, os.path.join(HERE, "..", "cli"))
import httpx, pytest

PORT = 8821
SENT = []


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    saved = {k: os.environ.get(k) for k in ("GINK_DB_PATH", "GROQ_API_KEY")}       # restored afterwards
    os.environ["GINK_DB_PATH"] = str(tmp_path_factory.mktemp("cli") / "c.db"); os.environ["GROQ_API_KEY"] = "g"
    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}, {"id": "openai/gpt-oss-20b"}]})
        body = json.loads(request.content); SENT.append(body)
        frames = [{"choices": [{"index": 0, "delta": {"content": p}}]} for p in ("Hello ", "from ", "Gink!")]
        sse = "".join("data: " + json.dumps(f) + "\n\n" for f in frames) + "data: [DONE]\n\n"
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
    real = httpx.AsyncClient
    class Mock(real):                                   # only the SERVER's calls to Groq are simulated
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    httpx.AsyncClient = Mock
    import uvicorn
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0); b._models_cache.update(data=None, at=0.0)
    srv = uvicorn.Server(uvicorn.Config(b.app, port=PORT, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start(); time.sleep(1.5)
    token = b._token_response("dev@example.com", "Dev")["token"]
    key = httpx.post(f"http://127.0.0.1:{PORT}/account/api-keys", json={"name": "cli"},
                     headers={"Authorization": f"Bearer {token}"}).json()["key"]
    yield key
    srv.should_exit = True; httpx.AsyncClient = real
    for k, v in saved.items():                     # leave the environment as we found it
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    b._groq_models.update(ids=set(), at=0.0); b._models_cache.update(data=None, at=0.0)


def gink(args, key, stdin=None, tmp="/tmp/gink-cli-home"):
    env = dict(os.environ, GINK_API_KEY=key, GINK_BASE_URL=f"http://127.0.0.1:{PORT}/v1", XDG_CONFIG_HOME=tmp,
               PYTHONPATH=os.path.join(HERE, "..", "cli"))
    return subprocess.run([sys.executable, "-m", "gink_cli"] + args, input=stdin, capture_output=True, text=True,
                          env=env, timeout=60)


def test_models_and_a_streamed_answer(server):
    r = gink(["models"], server)
    assert r.returncode == 0 and "gink-search" in r.stdout.split()
    r = gink(["What", "is", "Gink?"], server, stdin="")
    assert r.returncode == 0 and r.stdout.strip() == "Hello from Gink!"
    assert SENT[-1]["messages"][-1]["content"] == "What is Gink?"


def test_piped_text_and_web_search(server):
    r = gink(["summarise", "this"], server, stdin="Meeting notes: launch Gink in Dakar on Friday.")
    assert r.returncode == 0
    sent = SENT[-1]["messages"][-1]["content"]
    assert '<attached_file name="input">' in sent and "launch Gink in Dakar" in sent and sent.endswith("summarise this")
    gink(["-s", "latest", "news"], server, stdin="")
    assert SENT[-1]["tools"] == [{"type": "browser_search"}]                    # really a web search


def test_wrong_key_is_explained(server):
    r = gink(["hi"], "gink_live_not-a-real-key", stdin="")
    assert r.returncode == 1 and "isn't valid" in r.stderr and "gink login" in r.stderr
    r = gink(["hi"], "", stdin="", tmp="/tmp/gink-cli-empty")
    assert r.returncode == 1 and "No API key yet" in r.stderr


def test_chat_and_login(server, tmp_path, monkeypatch, capsys):
    from gink_cli import main as m
    base = f"http://127.0.0.1:{PORT}/v1"
    said = iter(["hello there", "/new", "/search on", "and the news?", "/exit"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(said))
    assert m.chat(server, base, "") == 0
    out = capsys.readouterr().out
    assert out.count("Hello from Gink!") == 2 and "New chat." in out and "Web search on." in out
    assert SENT[-1]["tools"] == [{"type": "browser_search"}] and len(SENT[-1]["messages"]) >= 1

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path)); monkeypatch.setenv("GINK_BASE_URL", base)
    monkeypatch.setattr(m.getpass, "getpass", lambda prompt="": server)
    assert m.login(base) == 0
    path = m.config_path()
    assert json.load(open(path))["api_key"] == server and stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_openapi_only_describes_the_developer_api(server):
    c = httpx.Client(base_url=f"http://127.0.0.1:{PORT}")
    for hidden in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(hidden).status_code == 404
    spec = c.get("/v1/openapi.json").json()
    assert spec["openapi"] == "3.1.0" and sorted(spec["paths"]) == ["/chat/completions", "/images/generations", "/models"]
    assert spec["servers"][0]["url"].endswith("/v1") and "admin" not in json.dumps(spec)
