"""Ring 2, offline: one call the agent really speaks, scored by DeepEval's voice metrics.

Everything else in `tests/evals` judges words. This judges sound: the reply is
synthesised by the project's ElevenLabs voice, played at wall-clock speed into
the stereo OGG the framework writes for a `--record` call, cut per turn and
handed to `AudioIntegrityMetric` and `AgentResponsivenessMetric`.

Neither metric is a judge — both are dependency-free DSP over the WAV
(`deepeval/metrics/voice/_detectors.py`), so they cost nothing and need no
model. What the test costs is the call itself: one Haiku turn and about two
hundred ElevenLabs characters.

What it does NOT assert is the integrity SCORE. On a five-second conversational
turn DeepEval counts every pause between words as a dropout — see `docs/evals.md`
§3.9 — so the score is 0.0 for any normal sentence and asserting on it would be
pinning the bug, not the audio. What is asserted is the part that means
something: no critical failure, no clipping, no loop, and sound on every reply.

Marked `flaky=True` on both metrics, as CLAUDE.md requires of a voice case: the
audio comes from a live provider over a live network.
"""

import os

import pytest

from convo.state.attach import attach_log
from convo.state.store import MemoryStore
from convo.testing.callers.audio import voice_case_from
from convo.testing.harness import fake_context, live_conversation

pytestmark = [pytest.mark.evals, pytest.mark.voice]

TENANT, PROJECT = "clinica-norte", "reagendamiento"
LINE = "Buenos días, llamo para cambiar una cita."
BENIGN = {"audio_dropout", "abrupt_cutoff"}  # prosody, not a defect — §3.9

needs_voice = pytest.mark.skipif(
    not (os.getenv("ELEVENLABS_API_KEY") and os.getenv("ANTHROPIC_API_KEY")),
    reason="a spoken call needs ELEVENLABS_API_KEY and ANTHROPIC_API_KEY",
)


@needs_voice
async def test_a_spoken_reply_reaches_the_recording_and_the_voice_metrics_can_read_it(
    tmp_path, monkeypatch
) -> None:
    """One turn, spoken, recorded, cut and scored — the whole ms-6 chain in one test."""
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)  # no microphone, nothing to transcribe
    tc = fake_context(TENANT, PROJECT, channel="voice")
    attach_log(tc, MemoryStore())
    async with live_conversation(tc, record=tmp_path / "audio.ogg") as call:
        await call.say(LINE)

    kinds = [event.kind for event in tc.log.events()]
    assert "audio.start" in kinds, "the recording never announced its origin"
    # the timed words only arrive when the session asked for the aligned transcript,
    # which `Recording` turns on because `build_session` reserves it for a microphone
    assert "tts.word" in kinds, kinds

    case = voice_case_from(tc.log.store, tc.session_id)
    spoken = [turn for turn in case.turns if turn.role == "assistant"]
    assert spoken and all(turn.audio is not None for turn in spoken), "a reply with no sound"

    integrity, responsiveness = _scored(case)
    print(f"\naudio integrity {integrity.score}: {integrity.reason}")
    print(f"agent responsiveness {responsiveness.score}: {responsiveness.reason}")

    assert responsiveness.score == 1.0, responsiveness.reason
    breakdown = integrity.score_breakdown
    assert not breakdown["critical_failure"], breakdown["events"]
    assert {event["type"] for event in breakdown["events"]} <= BENIGN, breakdown["events"]


def _scored(case):
    """Both voice metrics, measured on the case, flaky because a live provider made the audio."""
    from deepeval.metrics.voice import AgentResponsivenessMetric, AudioIntegrityMetric

    metrics = (AudioIntegrityMetric(flaky=True), AgentResponsivenessMetric(flaky=True))
    for metric in metrics:
        metric.measure(case, _show_indicator=False)
    return metrics
