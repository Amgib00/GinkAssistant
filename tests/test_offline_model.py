"""The desktop apps' offline model: the server can name a different one (e.g. Gink's own GGUF); it's
downloaded once and replaces the old one; answers use the model's own chat template."""
import asyncio
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


@pytest.fixture
def llm(tmp_path, monkeypatch):
    from ginkassistant.services import local_llm as L
    monkeypatch.setattr(L, "chosen", {"url": L.MODEL_URL, "name": "Llama 2 7B Chat"})
    monkeypatch.setattr(L, "data_dir", lambda app: tmp_path)
    got = []

    class Resp:
        def __init__(self, url): self.url = url
        def raise_for_status(self): pass
        async def aiter_bytes(self, chunk_size=0):
            yield b"GGUF" + self.url.encode()

    class Stream:
        def __init__(self, url): self.url = url
        async def __aenter__(self): got.append(self.url); return Resp(self.url)
        async def __aexit__(self, *a): return False

    class Client:
        def __init__(self, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def stream(self, method, url, follow_redirects=False): return Stream(url)
    monkeypatch.setattr(L.httpx, "AsyncClient", Client)
    return L, L.LocalLLM(object()), got, tmp_path


def test_default_then_the_servers_choice(llm):
    L, m, got, tmp = llm
    asyncio.run(m.ensure_model())
    assert got == [L.MODEL_URL] and json.loads((tmp / "models" / "model.json").read_text())["url"] == L.MODEL_URL
    asyncio.run(m.ensure_model())
    assert len(got) == 1                                                          # once
    gink = "https://huggingface.co/amgib/gink-4b-GGUF/resolve/main/gink-4b-q4_k_m.gguf"
    L.configure(gink, "Gink 4B")
    asyncio.run(m.ensure_model())
    assert got[-1] == gink and (tmp / "models" / "model.gguf").read_bytes().endswith(gink.encode())
    assert json.loads((tmp / "models" / "model.json").read_text()) == {"url": gink, "name": "Gink 4B"}
    assert not (tmp / "models" / "model.part").exists()


def test_files_from_before_count_as_the_default(llm):
    L, m, got, tmp = llm
    (tmp / "models").mkdir()
    (tmp / "models" / "model.gguf").write_bytes(b"old")
    asyncio.run(m.ensure_model())
    assert got == []                                                              # no surprise re-download


def test_only_https_gguf_addresses(llm):
    L, *_ = llm
    L.configure("http://example.com/x.gguf"); L.configure("https://example.com/x.bin")
    assert L.chosen["url"] == L.MODEL_URL


def test_answers_use_the_chat_template(llm, monkeypatch):
    L, m, got, tmp = llm
    monkeypatch.setattr(L, "HAS_LLAMA_CPP", True)
    seen = {}

    class Fake:
        def create_chat_completion(self, messages, max_tokens):
            seen["messages"] = messages
            return {"choices": [{"message": {"content": " Bonjour ! "}}]}
    m._llm = Fake()
    (tmp / "models").mkdir(exist_ok=True); (tmp / "models" / "model.gguf").write_bytes(b"x")
    assert asyncio.run(m.ask("Salut", system_prompt="You are Gink.")) == "Bonjour !"
    assert seen["messages"] == [{"role": "system", "content": "You are Gink."}, {"role": "user", "content": "Salut"}]

    class Old:
        def create_chat_completion(self, **k): raise ValueError("no template")
        def __call__(self, prompt, max_tokens, stop): return {"choices": [{"text": " hi "}]}
    m._llm = Old()
    assert asyncio.run(m.ask("hello")) == "hi"                                   # older files: plain prompt


def test_server_names_it(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "i.db"))
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    c = TestClient(b.app)
    monkeypatch.delenv("GINK_OFFLINE_MODEL_URL", raising=False)
    assert "offline_model" not in c.get("/info").json()
    monkeypatch.setenv("GINK_OFFLINE_MODEL_URL", "https://huggingface.co/x/y/resolve/main/g.gguf")
    assert c.get("/info").json()["offline_model"] == {"url": "https://huggingface.co/x/y/resolve/main/g.gguf",
                                                       "name": "Gink offline model"}
