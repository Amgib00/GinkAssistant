"""
Optional local GGUF inference via llama-cpp-python, used as a fallback
when GROQ_API_KEY isn't set.

Worth being upfront about this one: the original model_utils.py only
ever downloaded a GGUF file, and nothing found in the whole review
actually loaded or ran it with llama-cpp-python -- so there was no
existing consumer to port exactly. requirements.txt does confirm
llama-cpp-python is a real, intended dependency, so this is a reasonable
implementation of what that download was presumably for, built from
scratch rather than ported from working code.

Same mobile-risk flag as before, still true: llama-cpp-python is a
compiled C++ engine with no confirmed Android/iOS build story, and a 7B
model needs several GB of RAM most phones don't have free. This stays
fully optional (HAS_LLAMA_CPP) and is never the default path -- it's
only reached if Groq is unavailable.

Also fixes a real bug from the original: there, a failed model download
was treated as fatal and crashed the whole app's startup. Here, a failed
download just raises LocalLLMUnavailable, which the caller can catch and
fall back further, same as "no Groq key" already does.
"""

import asyncio
from typing import Optional

import httpx
import toga

from .paths import data_dir

try:
    from llama_cpp import Llama

    HAS_LLAMA_CPP = True
except ImportError:
    HAS_LLAMA_CPP = False

MODEL_FILENAME = "model.gguf"
MODEL_URL = "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf"
# Which model: the default above, or the one your Gink server names (GINK_OFFLINE_MODEL_URL in /info) --
# e.g. Gink's own fine-tuned GGUF (tools/gink_model/PLAN.md, step 6). models/model.json remembers which
# file is on disk, so a new choice downloads once and replaces the old one.
chosen = {"url": MODEL_URL, "name": "Llama 2 7B Chat"}


def configure(url: str = "", name: str = "") -> None:
    if url and url.startswith("https://") and url.endswith(".gguf"):
        chosen.update(url=url, name=name or "Gink offline model")


class LocalLLMUnavailable(Exception):
    pass


class LocalLLM:
    def __init__(self, app: toga.App):
        self.model_path = data_dir(app) / "models" / MODEL_FILENAME
        self._llm = None

    def _recorded_url(self) -> str:
        info = self.model_path.with_name("model.json")
        try:
            import json
            return json.loads(info.read_text(encoding="utf-8")).get("url", "")
        except Exception:
            return MODEL_URL if self.model_path.exists() else ""     # files from before model.json: the default

    def _record(self, url: str) -> None:
        import json
        self.model_path.with_name("model.json").write_text(json.dumps({"url": url, "name": chosen["name"]}),
                                                           encoding="utf-8")

    async def ensure_model(self, on_status=None):
        url = chosen["url"]
        if self.model_path.exists() and self._recorded_url() == url:
            return
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        if on_status:
            on_status(f"Downloading the offline model ({chosen['name']}, a few GB, one-time)...")

        tmp_path = self.model_path.with_suffix(".part")
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url, follow_redirects=True) as resp:
                    resp.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
            self._llm = None                                   # a loaded old model lets go of the file
            tmp_path.replace(self.model_path)
            self._record(url)
        except Exception as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise LocalLLMUnavailable(f"Couldn't download the local model: {exc}") from exc

    def _load(self):
        if self._llm is None:
            self._llm = Llama(model_path=str(self.model_path), n_ctx=2048, verbose=False)
        return self._llm

    async def ask(self, prompt: str, system_prompt: str = "", on_status=None) -> str:
        if not HAS_LLAMA_CPP:
            raise LocalLLMUnavailable("llama-cpp-python isn't installed on this build.")

        await self.ensure_model(on_status=on_status)
        loop = asyncio.get_event_loop()

        def _run():
            llm = self._load()
            try:                                              # the model's own chat template (Llama, Qwen...)
                messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + \
                           [{"role": "user", "content": prompt}]
                result = llm.create_chat_completion(messages=messages, max_tokens=512)
                text = (result["choices"][0]["message"].get("content") or "").strip()
                if text:
                    return text
            except Exception:
                pass
            full_prompt = f"{system_prompt}\n\nUser: {prompt}\nAssistant:" if system_prompt else prompt
            result = llm(full_prompt, max_tokens=512, stop=["User:"])
            return result["choices"][0]["text"].strip()

        return await loop.run_in_executor(None, _run)
