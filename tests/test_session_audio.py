"""Two shapes of session: voice when the providers exist, text-only (audio off) when they do not."""

import pytest

from core.providers import stt, tts
from core.session import (
    build_session,
    channel_options,
    start_session,
    text_turn_handling,
    voice_turn_handling,
)
from core.testing import fake_context
from tests.conftest import needs_llm

pytestmark = pytest.mark.unit


def test_voice_turn_handling_combines_soniox_endpointing_with_the_local_detector() -> None:
    options = voice_turn_handling()

    assert "mini" in options["turn_detection"].model
    endpointing, interruption = options["endpointing"], options["interruption"]
    assert (endpointing["min_delay"], endpointing["max_delay"]) == (0.3, 2.5)
    assert interruption["min_words"] == 2 and interruption["resume_false_interruption"] is True
    assert options["preemptive_generation"]["max_retries"] == 1


def test_text_turn_handling_has_no_turn_detector() -> None:
    assert text_turn_handling()["turn_detection"] is None


def test_a_chat_session_meets_the_room_with_no_audio_either_way() -> None:
    options = channel_options("chat")

    assert options.audio_input is False and options.audio_output is False


def test_a_voice_session_keeps_the_room_defaults() -> None:
    options = channel_options("voice")

    assert options.audio_input is not False and options.audio_output is not False


async def test_with_providers_and_a_vad_the_session_is_a_voice_session(monkeypatch) -> None:
    monkeypatch.setenv(stt.KEY_ENV, "sx-test")
    monkeypatch.setenv(tts.KEY_ENV, "el-test")
    from core.providers import vad_for

    tc = fake_context("clinica-norte", "reagendamiento")
    session = build_session(tc, vad=vad_for())

    assert session.stt is not None and session.tts is not None and session.vad is not None
    assert session.options.use_tts_aligned_transcript is True
    assert session.options.turn_handling["turn_detection"] is not None


async def test_without_providers_the_session_is_text_only(monkeypatch) -> None:
    monkeypatch.delenv(stt.KEY_ENV, raising=False)
    monkeypatch.delenv(tts.KEY_ENV, raising=False)
    tc = fake_context("clinica-norte", "reagendamiento")

    session = build_session(tc)

    assert session.stt is None and session.tts is None
    assert session.options.turn_handling["turn_detection"] is None


@needs_llm
async def test_text_only_session_switches_audio_off(monkeypatch):
    monkeypatch.delenv(stt.KEY_ENV, raising=False)
    monkeypatch.delenv(tts.KEY_ENV, raising=False)
    tc = fake_context("clinica-norte", "reagendamiento")
    session = build_session(tc)
    async with session:
        await start_session(session, tc.project.entry_agent(tc))
        assert session.output.audio_enabled is False
        assert session.input.audio_enabled is False
