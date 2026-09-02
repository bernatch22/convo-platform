"""Cutting a recording into turns: the arithmetic, with no provider and no model.

`core.testing.audio` is the only place where two clocks meet — the session log's
`t_ms` and the samples of the OGG — and getting the offset wrong is the kind of
mistake that shows up as a metric quietly scoring the wrong four seconds. So the
whole cut is exercised here against a stereo file this module builds itself: the
caller's channel silent, the agent's channel a tone in a known place.
"""

import io
import wave

import numpy as np
import pytest

from convo.state.events import Event
from convo.testing.callers.audio import (
    AGENT,
    CALLER,
    TAIL_MS,
    agent_windows,
    attach_audio,
    cut,
    recorded_path,
    split_channels,
)
from convo.testing.replay import turns_from

pytestmark = pytest.mark.unit

RATE = 16000
SECONDS = 10
TONE_FROM, TONE_TO = 2.0, 6.0  # where the "agent" speaks in the synthetic file


@pytest.fixture
def recording(tmp_path):
    """A 10 s stereo WAV: L silent, R a 440 Hz tone between 2 s and 6 s."""
    time = np.arange(RATE * SECONDS) / RATE
    tone = (8000 * np.sin(2 * np.pi * 440 * time)).astype(np.int16)
    tone[(time < TONE_FROM) | (time >= TONE_TO)] = 0
    stereo = np.stack([np.zeros_like(tone), tone], axis=1)
    path = tmp_path / "audio.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(stereo.tobytes())
    return path


def events(*rows: tuple[str, int, dict]) -> list[Event]:
    """A log, as `(kind, t_ms, payload)` rows numbered in order."""
    return [
        Event(seq=index + 1, kind=kind, t_ms=t_ms, payload=payload)
        for index, (kind, t_ms, payload) in enumerate(rows)
    ]


def test_the_two_channels_come_back_separately_at_the_files_own_rate(recording) -> None:
    channels, rate = split_channels(recording)

    assert rate == RATE
    assert channels.shape == (2, RATE * SECONDS)
    assert channels[CALLER].max() == 0  # nobody was recorded on the caller's side
    assert channels[AGENT].max() > 7000


def test_a_cut_is_clamped_to_what_the_file_holds_and_never_wraps(recording) -> None:
    channels, rate = split_channels(recording)

    assert len(cut(channels[AGENT], rate, 2.0, 6.0)) == 4 * RATE
    assert len(cut(channels[AGENT], rate, 9.0, 99.0)) == 1 * RATE  # past the end, clamped
    assert len(cut(channels[AGENT], rate, 7.0, 3.0)) == 0  # end before start is nothing


def test_an_agent_turn_runs_from_when_it_took_the_floor_to_when_it_was_committed() -> None:
    log = events(
        ("state", 1000, {"to": "speaking"}),
        ("turn.agent", 5000, {"text": "buenos días"}),
        ("turn.user", 6000, {"text": "hola"}),
        ("state", 7000, {"to": "speaking"}),
        ("turn.agent", 9000, {"text": "dígame"}),
    )

    assert agent_windows(log) == [(1000, 5000), (7000, 9000)]


def test_a_turn_that_never_took_the_floor_is_a_window_of_no_length() -> None:
    """A reply with no audio — a text-only turn — must not borrow the previous one's."""
    log = events(("turn.agent", 4000, {"text": "escrito, no hablado"}))

    assert agent_windows(log) == [(4000, 4000)]


def test_the_clip_of_a_turn_starts_where_the_log_says_the_recording_did(recording) -> None:
    """`audio.start` is the origin: a log that begins 500 ms before sample 0 must not slide."""
    log = events(
        ("session.start", 0, {}),
        ("audio.start", 500, {"path": str(recording)}),
        ("state", 2500, {"to": "speaking"}),
        ("turn.agent", 6500, {"text": "cuatro segundos de tono"}),
    )
    case = _case(log)

    attach_audio(case, log, recording)

    audio = case.turns[0].audio
    assert audio is not None and audio.start_time == 2.0
    assert audio.duration == pytest.approx(4.0 + TAIL_MS / 1000, abs=0.01)
    assert np.abs(_samples(audio)[: 4 * RATE]).max() > 7000  # the tone, not the silence


def test_the_caller_typed_so_the_user_turns_carry_no_audio_at_all(recording) -> None:
    log = events(
        ("audio.start", 0, {"path": str(recording)}),
        ("turn.user", 1000, {"text": "hola"}),
        ("state", 2000, {"to": "speaking"}),
        ("turn.agent", 6000, {"text": "buenos días"}),
    )
    case = _case(log)

    attach_audio(case, log, recording)

    assert [turn.audio is None for turn in case.turns] == [True, False]


def test_the_log_says_where_its_recording_went() -> None:
    log = events(("audio.start", 5, {"path": "tmp/a.ogg"}), ("session.end", 90, {"audio": "x.ogg"}))

    assert recorded_path(log) == "tmp/a.ogg"
    assert recorded_path(events(("session.start", 0, {}))) is None


def _case(log: list[Event]):
    """The replayed case for a log, without a store — `turns_from` is pure."""
    from deepeval.test_case import ConversationalTestCase

    return ConversationalTestCase(turns=turns_from(log), name="synthetic")


def _samples(audio) -> np.ndarray:
    """The PCM behind an `Audio`, as the metrics' decoder would read it."""
    with wave.open(io.BytesIO(audio.get_bytes()), "rb") as wav:
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
