"""The JavaScript SDK (sdk/js), run by Node against the real server on a local port (only the AI is simulated):
a managed agent in one call, live steps, workspaces, chat, errors."""
import json, os, shutil, subprocess, sys, threading, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import httpx
import pytest

PORT = 8823
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node 18+")


def _tool(name, **args):
    return {"id": f"c{time.time_ns()}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


@pytest.fixture(scope="module")
def key(tmp_path_factory):
    saved = {k: os.environ.get(k) for k in ("GINK_DB_PATH", "GROQ_API_KEY")}
    os.environ["GINK_DB_PATH"] = str(tmp_path_factory.mktemp("js") / "j.db"); os.environ["GROQ_API_KEY"] = "g"
    script = []

    def groq(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b"}, {"id": "openai/gpt-oss-20b"}]})
        body = json.loads(request.content)
        if body.get("tools"):                                       # the agent
            if not script:
                script.extend([{"content": "", "tool_calls": [_tool("write_file", path="report.md", content="# Report")]},
                               {"content": "Wrote report.md."}])
            msg = dict({"role": "assistant"}, **script.pop(0))
        else:                                                       # chat
            msg = {"role": "assistant", "content": "Hi from Gink."}
        return httpx.Response(200, json={"choices": [{"index": 0, "message": msg, "finish_reason": "stop"}]})
    real = httpx.AsyncClient

    class Mock(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(groq); super().__init__(*a, **k)
    httpx.AsyncClient = Mock
    import uvicorn
    from ginkassistant.services import backend_server as b
    b._groq_models.update(ids=set(), at=0.0); b._models_cache.update(data=None, at=0.0)
    srv = uvicorn.Server(uvicorn.Config(b.app, port=PORT, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start(); time.sleep(1.5)
    b._upsert_user("js@example.com", "JS", None, "password")
    yield b._create_api_key("js@example.com", "js")["key"]
    srv.should_exit = True; httpx.AsyncClient = real
    for k, v in saved.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    b._groq_models.update(ids=set(), at=0.0); b._models_cache.update(data=None, at=0.0)


SCRIPT = r'''
import { Gink, GinkAPIError } from "./index.js";
const gink = new Gink();
const out = {};
const it = await gink.interactions.create({ input: "Write a report", environment: "remote" });
out.status = it.status; out.text = it.output_text; out.files = it.files_changed;
const env = await gink.environments.get(it.environment);
out.download = await env.text("report.md");
await env.upload("data.csv", "a,b\n1,2\n");
out.uploaded = (await env.refresh()).files.map((f) => f.path).sort();
const events = [];
for await (const e of gink.interactions.stream({ input: "Again", previous_interaction_id: it.id })) events.push(e.type);
out.events = events;
out.chat = await gink.chat("Hello");
try { await new Gink({ apiKey: "gink_wrong" }).interactions.create({ input: "x" }); }
catch (e) { out.error = [e instanceof GinkAPIError, e.status, e.code]; }
const made = await gink.environments.create({ name: "tmp" });
await made.delete();
out.deleted = !(await gink.environments.list()).some((e) => e.id === made.id);
console.log(JSON.stringify(out));
'''


def test_js_sdk_against_the_server(key, tmp_path):
    sdk = os.path.join(HERE, "..", "sdk", "js")
    test = os.path.join(sdk, "_test_run.mjs")
    with open(test, "w", encoding="utf-8") as f:
        f.write(SCRIPT)
    try:
        r = subprocess.run(["node", test], cwd=sdk, capture_output=True, text=True, timeout=90,
                           env=dict(os.environ, GINK_API_KEY=key, GINK_BASE_URL=f"http://127.0.0.1:{PORT}/v1"))
    finally:
        os.remove(test)
    assert r.returncode == 0, r.stderr[-1500:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["status"] == "completed" and out["text"] == "Wrote report.md." and out["files"] == ["report.md"]
    assert out["download"] == "# Report" and out["uploaded"] == ["data.csv", "report.md"]
    assert "step" in out["events"] and out["events"][-1] == "done"
    assert out["chat"] == "Hi from Gink." and out["error"] == [True, 401, "invalid_api_key"] and out["deleted"] is True


def test_package_and_types_agree():
    sdk = os.path.join(HERE, "..", "sdk", "js")
    pkg = json.load(open(os.path.join(sdk, "package.json"), encoding="utf-8"))
    import tomllib
    with open(os.path.join(HERE, "..", "cli", "pyproject.toml"), "rb") as f:
        assert pkg["version"] == tomllib.load(f)["project"]["version"]        # Python and JS SDKs move together
    dts = open(os.path.join(sdk, "index.d.ts"), encoding="utf-8").read()
    for name in ("stream(params", "wait(id", "upload(path", "download(path", "chat(message", "GinkAPIError"):
        assert name in dts
