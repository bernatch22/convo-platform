"""Transcript gate: a final transcript must have audible speech behind it, or it never happened.

Decisions: docs/decisions/convo.session.stt_gate.md
"""

import math
import time
from collections import deque
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass

import numpy as np
from livekit import rtc
from livekit.agents import stt

FULL_SCALE = 32768.0  # int16
SILENT_DB = -90.0  # what digital silence is called, so the arithmetic stays finite
MIN_SPEECH_DB = -55.0  # the quietest the gate will ever call speech
MAX_SPEECH_DB = -40.0  # the loudest it will ever demand — a whisper on a bad line still passes
FLOOR_FALL = 0.35  # per frame, toward a quieter line: ~100 ms to settle
FLOOR_RISE = 0.004  # per frame, toward a louder one: speech cannot lift the floor

# The transcript kinds worth gating. INTERIM is a hypothesis the framework
# never commits a turn on, and dropping it would only make the live captions
# flicker differently; PREFLIGHT is what preemptive generation reads.
GATED = (stt.SpeechEventType.FINAL_TRANSCRIPT, stt.SpeechEventType.PREFLIGHT_TRANSCRIPT)


@dataclass(frozen=True)
class GateOptions:
    """How much real audio a transcript must have behind it. Zero switches a check off."""

    min_voiced_ms: float = 100.0
    max_lag_s: float = 2.5
    margin_db: float = 12.0


def gate_options_for(project) -> GateOptions:
    """The project's own thresholds over the platform's; `{}` keeps the platform's."""
    known = GateOptions.__dataclass_fields__
    edits = getattr(project, "stt_gate", None) or {}
    return GateOptions(**{k: float(v) for k, v in edits.items() if k in known})


def level_db(frame: rtc.AudioFrame) -> float:
    """One frame's RMS level in dBFS; digital silence answers `SILENT_DB`, never `-inf`."""
    samples = np.frombuffer(frame.data, dtype=np.int16)
    if samples.size == 0:
        return SILENT_DB
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    if rms <= 0:
        return SILENT_DB
    return max(20.0 * math.log10(rms / FULL_SCALE), SILENT_DB)


class TranscriptGate:
    """Measures the audio going into an STT and refuses the transcripts it cannot account for."""

    def __init__(self, options: GateOptions | None = None, clock=time.monotonic) -> None:
        self.options = options or GateOptions()
        self.clock = clock
        self.dropped = 0
        self.floor_db: float | None = None
        self._voiced: deque[tuple[float, float]] = deque()  # (heard at, ms of audio)
        self._voiced_ms = 0.0

    async def hear(self, frames: AsyncIterable[rtc.AudioFrame]) -> AsyncIterator[rtc.AudioFrame]:
        """Yield every frame exactly as it arrived, measuring it on the way past."""
        async for frame in frames:
            self.measure(frame)
            yield frame

    def measure(self, frame: rtc.AudioFrame) -> bool:
        """Take one frame into the window; True when it carried speech-level energy."""
        level = level_db(frame)
        voiced = level > self.threshold_db()
        self._track_floor(level)
        if voiced and frame.sample_rate:
            self._remember(1000.0 * frame.samples_per_channel / frame.sample_rate)
        return voiced

    def threshold_db(self) -> float:
        """The level a frame must beat to count as speech, clamped into the safe band."""
        floor = self.floor_db if self.floor_db is not None else SILENT_DB
        return min(max(floor + self.options.margin_db, MIN_SPEECH_DB), MAX_SPEECH_DB)

    def voiced_ms(self) -> float:
        """Milliseconds of speech-level audio inside the window that ends now."""
        self._forget_old()
        return self._voiced_ms

    def accepts(self, event: stt.SpeechEvent) -> bool:
        """True when this event may reach the session; False drops it as a hallucination."""
        if event.type not in GATED or not self._text_of(event):
            return True
        if self.options.min_voiced_ms <= 0 or self.voiced_ms() >= self.options.min_voiced_ms:
            return True
        self.dropped += 1
        return False

    def evidence(self, event: stt.SpeechEvent) -> dict:
        """What the gate saw when it refused an event — the payload of a `stt.phantom` log line."""
        alternative = event.alternatives[0] if event.alternatives else None
        return {
            "text": self._text_of(event),
            "language": getattr(alternative, "language", None),
            "confidence": round(float(getattr(alternative, "confidence", 0.0) or 0.0), 3),
            "voiced_ms": round(self.voiced_ms(), 1),
            "threshold_db": round(self.threshold_db(), 1),
            "window_s": self.options.max_lag_s,
        }

    def _remember(self, duration_ms: float) -> None:
        self._voiced.append((self.clock(), duration_ms))
        self._voiced_ms += duration_ms

    def _forget_old(self) -> None:
        cutoff = self.clock() - self.options.max_lag_s
        while self._voiced and self._voiced[0][0] < cutoff:
            self._voiced_ms -= self._voiced.popleft()[1]
        self._voiced_ms = max(self._voiced_ms, 0.0)

    def _track_floor(self, level: float) -> None:
        if self.floor_db is None:
            self.floor_db = level
            return
        rate = FLOOR_FALL if level < self.floor_db else FLOOR_RISE
        self.floor_db += (level - self.floor_db) * rate

    def _text_of(self, event: stt.SpeechEvent) -> str:
        return event.alternatives[0].text.strip() if event.alternatives else ""
