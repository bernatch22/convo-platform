"""Shared fixtures: load .env, provide a judge LLM, and keep the unit ring offline.

The unit ring is structurally unable to reach a provider: an autouse fixture
strips the LLM/STT/TTS keys from the environment for every unit test that has
not explicitly opted in (`needs_llm`, `voice`). A judged assertion that lands
in the wrong ring now fails in seconds with a missing-key error instead of
hanging the fast suite against the network (2026-08-30, four zombie pytests).
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv(".env")

# Not deleted but replaced: constructing a client still works (plenty of unit
# tests build sessions), while any REAL request dies at once with a 401.
OFFLINE_KEY = "offline-unit-ring-no-provider-calls"
# OPENAI too: deepeval's ToolCorrectnessMetric (deterministic!) still constructs
# a default OpenAI judge and demands a key it will never use.
LLM_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
VOICE_KEYS = ("SONIOX_API_KEY", "ELEVENLABS_API_KEY", "ELEVEN_API_KEY")


# Marks a test as LLM-backed: skipped without a key, exempt from the unit-ring strip.
needs_llm = pytest.mark.needs_llm


def pytest_collection_modifyitems(items):
    """Skip LLM-backed tests when there is no key to back them."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return
    skip = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set (LLM-backed test)")
    for item in items:
        if "needs_llm" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def unit_ring_is_offline(request, monkeypatch):
    """Strip provider keys inside unit tests so a misplaced network call dies at once."""
    if "unit" not in request.keywords:
        return
    if "needs_llm" not in request.keywords:
        for key in LLM_KEYS:
            monkeypatch.setenv(key, OFFLINE_KEY)
    if "voice" not in request.keywords:
        for key in VOICE_KEYS:
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def judge_llm():
    """A Claude Haiku instance used only to judge intents in tests."""
    from livekit.plugins import anthropic

    # 400, not 200: the judge answers by CALLING check_intent(success, reason), and a
    # reason written in Spanish about a three-sentence reply runs past 200 tokens — the
    # call never closes and the failure reads "LLM did not return any arguments".
    return anthropic.LLM(model="claude-haiku-4-5", max_tokens=400)
