"""Shared fixtures: load .env, provide a judge LLM, skip LLM tests without a key."""

import os

import pytest
from dotenv import load_dotenv

load_dotenv(".env")

needs_llm = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set (LLM-backed test)"
)


@pytest.fixture
def judge_llm():
    """A Claude Haiku instance used only to judge intents in tests."""
    from livekit.plugins import anthropic

    return anthropic.LLM(model="claude-haiku-4-5", max_tokens=200)
