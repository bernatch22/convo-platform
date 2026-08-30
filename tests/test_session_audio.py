"""A project without STT/TTS runs with audio switched off, so `console` (audio mode) survives."""

import pytest

from core.session import build_session, start_session
from core.testing import fake_context
from tests.conftest import needs_llm

pytestmark = [pytest.mark.unit, needs_llm]


async def test_text_only_session_switches_audio_off():
    tc = fake_context("clinica-norte", "reagendamiento")
    session = build_session(tc)
    async with session:
        await start_session(session, tc.project.entry_agent(tc))
        assert session.tts is None and session.stt is None
        assert session.output.audio_enabled is False
        assert session.input.audio_enabled is False
