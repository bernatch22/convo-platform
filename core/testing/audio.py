"""Ring 3, with the audio: a recorded session as a ConversationalTestCase that carries sound.

`core.testing.replay` rebuilds what was SAID from the append-only log. This
adds what was HEARD: the stereo OGG a `--record` call leaves behind, cut into
one clip per agent turn and hung on the turns the replay already built, so
DeepEval's `AudioIntegrityMetric` and `AgentResponsivenessMetric` have
something to measure.

Three facts make the cut possible, and all three are in the log:

  `audio.start`   its `t_ms` is the log time of sample 0 of the OGG — the one
                  number that ties the two clocks together
  `state`         `to: speaking` is the millisecond the agent took the floor
  `turn.agent`    written when the item is committed, i.e. once its audio has
                  played out — so it is the END of the window, not the start

What is deliberately NOT used: `tts.word`'s `t1`. ElevenLabs sends alignment
relative to each websocket chunk and the framework never rebases it, so `t1`
is a word's place inside its own chunk and cannot address the file. See
`core.observability.voice.TimedWords`.

The caller's channel (L) is whatever the microphone put there — silence on an
offline run, where the caller typed. User turns therefore get no `Audio` at
all rather than a clip of silence that would read as a broken microphone.

Open source note: PyAV decodes both OGG/Opus and WAV, and PyAV is already a
livekit-agents dependency, so this adds nothing to install. Nothing below
knows about tenants or about LiveKit.
"""

import io
import wave
from collections.abc import Mapping
from pathlib import Path

import av
import numpy as np
from deepeval.test_case import Audio, ConversationalTestCase

from core.state.events import Event
from core.state.store import Store
from core.testing import replay

CALLER, AGENT = 0, 1
TAIL_MS = 250  # a sentence's decay lands after the item is committed; cutting it reads as clipped


def voice_case_from(
    store: Store,
    session_id: str,
    ogg_path: str | Path | None = None,
    descriptions: Mapping[str, str] | None = None,
) -> ConversationalTestCase:
    """One recorded session as the case the offline voice metrics score.

    The turns, the tool calls and the scenario are `replay`'s; this only adds
    the agent's audio. `ogg_path` defaults to the file the session log itself
    names, so a caller with a session id needs nothing else.
    """
    events = store.events(session_id)
    case = replay.conversational_case_from(store, session_id, descriptions)
    path = ogg_path or recorded_path(events)
    if path:
        attach_audio(case, events, path)
    return case


def recorded_path(events: list[Event]) -> str | None:
    """Where this session's audio went, as `session.end` (or `audio.start`) recorded it."""
    for event in events:
        if event.kind in ("session.end", "audio.start"):
            found = event.payload.get("audio") or event.payload.get("path")
            if found:
                return str(found)
    return None


def attach_audio(case: ConversationalTestCase, events: list[Event], path: str | Path) -> None:
    """Cut the agent channel by turn and hang one clip on each assistant turn, in order."""
    channels, rate = split_channels(path)
    origin_ms = _origin_ms(events)
    windows = agent_windows(events)
    turns = [turn for turn in case.turns if turn.role == "assistant"]
    for turn, (start_ms, end_ms) in zip(turns, windows, strict=False):
        start, end = (start_ms - origin_ms) / 1000, (end_ms - origin_ms + TAIL_MS) / 1000
        clip = cut(channels[AGENT], rate, start, end)
        if clip.size == 0:
            continue
        turn.audio = Audio.from_bytes(
            wav_bytes(clip, rate),
            "audio/wav",
            sampleRate=rate,
            encoding="wav",
            duration=len(clip) / rate,
            start_time=max(0.0, start),
        )


def agent_windows(events: list[Event]) -> list[tuple[int, int]]:
    """One `(from_ms, to_ms)` per `turn.agent`: the floor it took, up to the item's commit.

    The agent's audio does not start when its turn is written — the turn is
    written when the audio has finished. The last `state → speaking` before the
    commit is where the sound begins; a turn with no speaking state before it
    (a text-only reply, or one the caller cut off before a word came out) is
    reported as an empty window and simply carries no audio.
    """
    windows: list[tuple[int, int]] = []
    speaking: int | None = None
    for event in events:
        if event.kind == "state" and event.payload.get("to") == "speaking":
            speaking = event.t_ms
        elif event.kind == "turn.agent":
            windows.append((speaking if speaking is not None else event.t_ms, event.t_ms))
            speaking = None
    return windows


def split_channels(path: str | Path) -> tuple[np.ndarray, int]:
    """The file's channels as `(2, n)` int16 at its own rate; a mono file is duplicated.

    Every frame goes through one resampler to planar 16-bit stereo, so the OGG
    the recorder writes (Opus, float planar) and the synthetic WAVs the unit
    test builds (packed integer) arrive at the cutting below in one shape.
    PyAV 18's `to_ndarray` takes no format argument — the resampler is the
    conversion.
    """
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        rate = stream.rate or 48000
        resampler = av.AudioResampler(format="s16p", layout="stereo", rate=rate)
        blocks = [
            frame.to_ndarray()
            for decoded in container.decode(stream)
            for frame in resampler.resample(decoded)
        ]
        blocks.extend(frame.to_ndarray() for frame in resampler.resample(None))
    if not blocks:
        return np.zeros((2, 0), dtype=np.int16), rate
    return np.concatenate(blocks, axis=1).astype(np.int16), rate


def cut(samples: np.ndarray, rate: int, start_s: float, end_s: float) -> np.ndarray:
    """The slice of one channel between two times, clamped to what the file actually holds."""
    lo = max(0, int(round(start_s * rate)))
    hi = min(len(samples), int(round(end_s * rate)))
    return samples[lo:hi] if hi > lo else samples[:0]


def wav_bytes(samples: np.ndarray, rate: int) -> bytes:
    """One mono channel as a 16-bit PCM WAV — the only format DeepEval's decoder accepts."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.astype("<i2").tobytes())
    return buffer.getvalue()


def _origin_ms(events: list[Event]) -> int:
    """The log time of sample 0 of the recording; 0 when the log never said."""
    for event in events:
        if event.kind == "audio.start":
            return event.t_ms
    return 0
