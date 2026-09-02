"""What was HEARD: a session's sound, cut into the clips a turn carries.

Decisions: docs/decisions/convo.testing.callers.audio.md
"""

import io
import wave
from collections.abc import Mapping
from pathlib import Path

import av
import numpy as np
from deepeval.test_case import Audio, ConversationalTestCase

from convo.state.events import Event
from convo.state.store import Store
from convo.testing import replay

CALLER, AGENT = 0, 1
TAIL_MS = 250  # a sentence's decay lands after the item is committed; cutting it reads as clipped


def voice_case_from(
    store: Store,
    session_id: str,
    ogg_path: str | Path | None = None,
    descriptions: Mapping[str, str] | None = None,
) -> ConversationalTestCase:
    """One recorded session as the case the offline voice metrics score."""
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
        turn.audio = audio_clip(clip, rate, start_time=max(0.0, start))


def agent_windows(events: list[Event]) -> list[tuple[int, int]]:
    """One `(from_ms, to_ms)` per `turn.agent`: the floor it took, up to the item's commit."""
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
    """The file's channels as `(2, n)` int16 at its own rate; a mono file is duplicated."""
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


def audio_clip(samples: np.ndarray, rate: int, start_time: float) -> Audio:
    """One channel's slice as the `Audio` a turn carries, `start_time` always set."""
    return Audio.from_bytes(
        wav_bytes(samples, rate),
        "audio/wav",
        sampleRate=rate,
        encoding="wav",
        duration=len(samples) / rate,
        start_time=max(0.0, start_time),
    )


class Timeline:
    """Audio arriving live, placed on the wall clock it arrived on."""

    def __init__(self, rate: int, origin: float) -> None:
        self.rate = rate
        self.origin = origin
        self._samples = np.zeros(0, dtype=np.int16)

    def add(self, samples: np.ndarray, at: float) -> None:
        """Write one frame at the second it arrived, growing the silence before it if needed."""
        start = max(0, int(round((at - self.origin) * self.rate)))
        end = start + len(samples)
        if end > len(self._samples):
            pad = np.zeros(end - len(self._samples), dtype=np.int16)
            self._samples = np.concatenate([self._samples, pad])
        self._samples[start:end] = samples

    def clip(self, from_wall: float, to_wall: float) -> np.ndarray:
        """The samples between two wall-clock times, clamped to what actually arrived."""
        return cut(self._samples, self.rate, from_wall - self.origin, to_wall - self.origin)

    def audio(self, from_wall: float, to_wall: float) -> Audio | None:
        """That slice as a turn's `Audio`, offset from the start of the call; None if empty."""
        clip = self.clip(from_wall, to_wall)
        if clip.size == 0:
            return None
        return audio_clip(clip, self.rate, start_time=from_wall - self.origin)


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
