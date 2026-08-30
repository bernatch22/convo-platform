"""Shared fixtures: load .env, provide a judge LLM, skip LLM tests without a key."""

import os

import pytest
from dotenv import load_dotenv

load_dotenv(".env")


@pytest.fixture(autouse=True)
def text_only_providers(request, monkeypatch):
    """Unit tests run text-only sessions even when the voice keys are in .env.

    With SONIOX/ELEVENLABS keys present, `build_session` builds a voice session,
    and a harness session outside a job context has no http_context for the
    STT websocket — the turn still answers, but through retries and error
    noise. Tests that really want the voice providers mark themselves `voice`.
    """
    if "voice" in request.keywords:
        return
    for key in ("SONIOX_API_KEY", "ELEVENLABS_API_KEY", "ELEVEN_API_KEY"):
        monkeypatch.delenv(key, raising=False)


needs_llm = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set (LLM-backed test)"
)


@pytest.fixture
def judge_llm():
    """A Claude Haiku instance used only to judge intents in tests."""
    from livekit.plugins import anthropic

    # 400, not 200: the judge answers by CALLING check_intent(success, reason), and a
    # reason written in Spanish about a three-sentence reply runs past 200 tokens — the
    # call never closes and the failure reads "LLM did not return any arguments".
    return anthropic.LLM(model="claude-haiku-4-5", max_tokens=400)
