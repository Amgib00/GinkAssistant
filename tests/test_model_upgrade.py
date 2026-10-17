"""Groq retired llama-3.3-70b-versatile and llama-3.1-8b-instant (16 Aug 2026). Old app builds still ask
for them: the server swaps in current models; GPT-OSS gets room to reason on short answers."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest

LIVE = {"openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b", "whisper-large-v3", "groq/compound"}


@pytest.fixture
def b(monkeypatch, tmp_path):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "m.db"))
    from ginkassistant.services import backend_server as b
    return b


def run(coro):
    return asyncio.run(coro)


def test_retired_models_are_swapped_for_current_ones(b, monkeypatch):
    async def live(): return LIVE
    monkeypatch.setattr(b, "_live_groq_models", live)
    assert run(b._current_model("llama-3.3-70b-versatile")) == "openai/gpt-oss-120b"      # the actions agent
    assert run(b._current_model("llama-3.1-8b-instant")) == "openai/gpt-oss-20b"          # chat titles
    assert run(b._current_model("openai/gpt-oss-20b")) == "openai/gpt-oss-20b"            # current: untouched
    assert run(b._current_model("some/unknown-model")) == "openai/gpt-oss-120b"           # best available
    # a photo sent to a text-only or retired model goes to a vision model Groq still offers
    assert run(b._current_model("openai/gpt-oss-120b", needs_vision=True)) == "qwen/qwen3.6-27b"
    assert run(b._current_model("meta-llama/llama-4-scout-17b-16e-instruct", needs_vision=True)) == "qwen/qwen3.6-27b"


def test_without_the_live_list_known_retirements_are_still_fixed(b, monkeypatch):
    async def none(): return set()
    monkeypatch.setattr(b, "_live_groq_models", none)
    assert run(b._current_model("llama-3.3-70b-versatile")) == "openai/gpt-oss-120b"
    assert run(b._current_model("openai/gpt-oss-20b")) == "openai/gpt-oss-20b"


def test_short_gpt_oss_answers_get_room_to_reason(b):
    title = {"model": "openai/gpt-oss-20b", "max_tokens": 24}
    b._fit_reasoning(title, 1024)
    assert title["reasoning_effort"] == "low" and title["max_tokens"] >= 280
    long_answer = {"model": "openai/gpt-oss-120b", "max_tokens": 1024}
    b._fit_reasoning(long_answer, 1024)
    assert "reasoning_effort" not in long_answer and long_answer["max_tokens"] == 1024
    other = {"model": "qwen/qwen3.6-27b", "max_tokens": 24}
    b._fit_reasoning(other, 1024)
    assert other == {"model": "qwen/qwen3.6-27b", "max_tokens": 24}


def test_app_defaults_are_current_models():
    from ginkassistant.services.actions import agent
    from ginkassistant.services.groq_worker import GroqBrain
    retired = {"llama-3.3-70b-versatile", "llama-3.1-8b-instant"}
    assert agent.DEFAULT_MODEL not in retired
    assert GroqBrain.TITLE_MODELS[0] == "openai/gpt-oss-20b"
    args = GroqBrain._short_answer_args("openai/gpt-oss-20b", 24)
    assert args["max_tokens"] >= 280 and args["extra_body"] == {"reasoning_effort": "low"}
