"""The phantom turn: a transcript with no audio behind it never becomes a user turn.

The regression this file pins is a real one. On the human's call
AJ_rt86KogpPxDa (2026-08-31, seq 9) Soniox emitted a final `"Thank you."` over
the opening comfort noise, 3.32 s after anyone had last made a sound, and the
agent answered "De nada" to nobody. `core.stt_gate` refuses that transcript in
`TenantAgent.stt_node`; these tests prove it refuses THAT one and keeps every
transcript a caller actually earned.

Two rings in one file, on purpose. The first half measures the arithmetic on
frames, with the clock in the test's hand. The second is the voice golden: a
real `AgentSession` running the framework's own audio path with a scripted STT
that hallucinates, asserted twice — gate on, gate off — so a green run cannot
be a test that proves nothing.

No key, no room, no billed audio: `core.testing.stt_script` builds both the
microphone and the STT.
"""

import asyncio
import dataclasses

import pytest
from livekit.agents import AgentSession, stt

from core.agents.base import TenantAgent
from core.observability.observers import observe
from core.session import text_turn_handling
from core.state.attach import attach_log
from core.state.store import MemoryStore
from core.stt_gate import MAX_SPEECH_DB, MIN_SPEECH_DB, GateOptions, TranscriptGate, level_db
from core.testing.harness import fake_context
from core.testing.stt_script import (
    ScriptedMicrophone,
    ScriptedSTT,
    Utterance,
    comfort_noise,
    speech,
    speech_event,
)

pytestmark = pytest.mark.unit

PHANTOM = "Thank you."  # what Soniox actually said it heard, in English, on a Spanish line
REAL = "Buenos días, llamo para cambiar una cita."
SETTLE_S = 0.6  # long enough for the scripted final to cross the whole audio path


class Clock:
    """A stopwatch the test winds by hand, so a 3-second lag costs no seconds."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


def final(text: str = PHANTOM, language: str = "en") -> stt.SpeechEvent:
    return speech_event(Utterance(text=text, language=language))


def feed(gate: TranscriptGate, frames, clock: Clock | None = None) -> None:
    """Push frames through the gate, advancing the test clock by each frame's duration."""
    for frame in frames:
        gate.measure(frame)
        if clock is not None:
            clock.tick(frame.samples_per_channel / frame.sample_rate)


# --- the arithmetic ----------------------------------------------------------


def test_a_transcript_over_comfort_noise_alone_is_refused() -> None:
    clock = Clock()
    gate = TranscriptGate(clock=clock)
    feed(gate, comfort_noise(3.0), clock)

    assert gate.accepts(final()) is False
    assert gate.dropped == 1
    assert gate.evidence(final())["voiced_ms"] == 0.0


def test_a_transcript_over_real_speech_is_believed() -> None:
    clock = Clock()
    gate = TranscriptGate(clock=clock)
    feed(gate, comfort_noise(1.0) + speech(0.5), clock)

    assert gate.accepts(final(REAL, "es")) is True
    assert gate.dropped == 0


def test_a_final_that_arrives_long_after_the_speech_is_refused() -> None:
    """The 3.32 s transcription delay of the real call, with no new sound in between."""
    clock = Clock()
    gate = TranscriptGate(clock=clock)
    feed(gate, speech(0.5), clock)
    clock.tick(3.32)

    assert gate.accepts(final()) is False


def test_two_finals_for_one_utterance_both_pass() -> None:
    """Soniox segments a sentence into several finals; the second is not a phantom."""
    clock = Clock()
    gate = TranscriptGate(clock=clock)
    feed(gate, speech(1.5), clock)

    assert gate.accepts(final("Buenos días,", "es")) is True
    clock.tick(0.05)
    assert gate.accepts(final("llamo para cambiar una cita.", "es")) is True


def test_a_quiet_caller_on_a_quiet_line_still_gets_through() -> None:
    """The threshold follows the line: 20 dB above its own hiss is speech, however faint."""
    clock = Clock()
    gate = TranscriptGate(clock=clock)
    feed(gate, comfort_noise(1.0, level_db=-75.0), clock)
    feed(gate, speech(0.4, level_db=-50.0), clock)

    assert gate.accepts(final(REAL, "es")) is True


def test_the_threshold_never_leaves_its_band() -> None:
    """However loud or dead the line, the bar stays where speech can clear it."""
    dead = TranscriptGate()
    feed(dead, comfort_noise(0.5, level_db=-90.0))
    loud = TranscriptGate()
    feed(loud, comfort_noise(0.5, level_db=-10.0))

    assert dead.threshold_db() == MIN_SPEECH_DB
    assert loud.threshold_db() == MAX_SPEECH_DB


def test_everything_that_is_not_a_transcript_passes_untouched() -> None:
    """Start and end of speech, usage, an empty final: the framework's business, not ours."""
    gate = TranscriptGate()
    feed(gate, comfort_noise(1.0))

    assert gate.accepts(stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)) is True
    assert gate.accepts(stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)) is True
    assert gate.accepts(speech_event(Utterance(text="  "))) is True
    assert gate.dropped == 0


def test_an_interim_hypothesis_is_never_gated() -> None:
    """Interims commit no turn; dropping them would only make the live captions lie."""
    gate = TranscriptGate()
    feed(gate, comfort_noise(1.0))

    assert gate.accepts(speech_event(Utterance(text=PHANTOM, final=False))) is True


def test_a_project_can_switch_the_gate_off() -> None:
    gate = TranscriptGate(GateOptions(min_voiced_ms=0))
    feed(gate, comfort_noise(1.0))

    assert gate.accepts(final()) is True


def test_silence_is_named_not_infinite() -> None:
    """A frame of digital zeroes must answer a number the arithmetic can carry."""
    frame = comfort_noise(0.01, level_db=-90.0)[0]

    assert level_db(frame) > float("-inf")


# --- the voice golden: the whole audio path, gate on and gate off ------------


async def test_a_session_opening_in_silence_produces_no_phantom_user_turn() -> None:
    """The regression: comfort noise in, a hallucinated final out, and nothing reaches the turn."""
    log = await _call(mic_frames=comfort_noise(0.3), heard=PHANTOM)

    assert "stt.final" not in log, "the phantom became a user turn"
    assert "stt.phantom" in log, "the phantom was dropped without a word in the log"


async def test_the_same_call_without_the_gate_does_answer_the_phantom() -> None:
    """The control: with `stt_gate` off the bug is still there, so the golden proves something."""
    log = await _call(mic_frames=comfort_noise(0.3), heard=PHANTOM, stt_gate={"min_voiced_ms": 0})

    assert "stt.final" in log
    assert "stt.phantom" not in log


async def test_real_speech_still_reaches_the_session_in_both_languages() -> None:
    """Criterion 2: the gate is about audio, not about language or wording."""
    for text, language in ((REAL, "es"), ("Hello, I would like to reschedule.", "en")):
        log = await _call(
            mic_frames=comfort_noise(0.3) + speech(0.6), heard=text, language=language
        )
        assert "stt.final" in log, f"{language}: real speech was refused"
        assert "stt.phantom" not in log


async def _call(
    mic_frames, heard: str, language: str = "en", stt_gate: dict | None = None
) -> list[str]:
    """One headless session — scripted microphone, scripted STT — and the kinds it logged."""
    tc = attach_log(fake_context("clinica-norte", "reagendamiento", channel="voice"), MemoryStore())
    tc.project = dataclasses.replace(tc.project, stt_gate=stt_gate or {})
    session = AgentSession(
        llm=None,
        stt=ScriptedSTT([Utterance(text=heard, after_s=0.2, language=language)]),
        turn_handling=text_turn_handling(),
        userdata=tc,
    )
    observe(session, tc)
    session.input.audio = ScriptedMicrophone(mic_frames)
    await session.start(Mute(tc))
    try:
        await asyncio.sleep(SETTLE_S)
    finally:
        await session.aclose()
    return [event.kind for event in tc.log.events()]


class Mute(TenantAgent):
    """A stage that says nothing on entry: this suite is about what the session HEARS."""

    def __init__(self, tc) -> None:
        super().__init__(tc, instructions="No hables.")

    async def on_enter(self) -> None:
        """Enter without a greeting and without an LLM turn — there is no LLM in this session."""
        self.tc.prev_agent = self
