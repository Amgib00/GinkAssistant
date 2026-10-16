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


class LocalLLMUnavailable(Exception):
    pass


class LocalLLM:
    def __init__(self, app: toga.App):
        self.model_path = data_dir(app) / "models" / MODEL_FILENAME
        self._llm = None

    async def ensure_model(self, on_status=None):
        if self.model_path.exists():
            return
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        if on_status:
            on_status("Downloading local model (several GB, one-time)...")

        tmp_path = self.model_path.with_suffix(".part")
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", MODEL_URL) as resp:
                    resp.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
            tmp_path.rename(self.model_path)
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
            full_prompt = f"{system_prompt}\n\nUser: {prompt}\nAssistant:" if system_prompt else prompt
            result = llm(full_prompt, max_tokens=512, stop=["User:"])
            return result["choices"][0]["text"].strip()

        return await loop.run_in_executor(None, _run)
