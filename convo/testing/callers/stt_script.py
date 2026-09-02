"""A microphone and an STT that can be told exactly what to hear, and when.

Decisions: docs/decisions/convo.testing.callers.stt_script.md
"""

import asyncio
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from livekit import rtc
from livekit.agents import stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions
from livekit.agents.voice import io

SAMPLE_RATE = 16000
FRAME_MS = 10
FULL_SCALE = 32768.0
HOLD_S = 30.0  # how long a spent microphone keeps the line open before the test ends it


@dataclass
class Utterance:
    """One thing the STT decides it heard: the text, and how long after the stream opened."""

    text: str
    after_s: float = 0.0
    language: str = "es"
    confidence: float = 0.9
    final: bool = True


class ScriptedSTT(stt.STT):
    """A streaming STT that transcribes the script it was given, not the audio it was fed."""

    def __init__(self, script: Sequence[Utterance]) -> None:
        super().__init__(capabilities=stt.STTCapabilities(streaming=True, interim_results=True))
        self.script = list(script)

    @property
    def model(self) -> str:
        return "scripted"

    @property
    def provider(self) -> str:
        return "core.testing"

    def stream(
        self,
        *,
        language=NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        """A stream that will speak the script and swallow every frame pushed at it."""
        return ScriptedStream(self, self.script, conn_options=conn_options)

    async def _recognize_impl(self, buffer, *, language=NOT_GIVEN, conn_options=None):
        raise NotImplementedError("ScriptedSTT is streaming only")


class ScriptedStream(stt.RecognizeStream):
    """Plays one script into the event channel while draining whatever audio arrives."""

    def __init__(
        self,
        parent: stt.STT,
        script: Sequence[Utterance],
        *,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(stt=parent, conn_options=conn_options)
        self._script = list(script)

    async def _run(self) -> None:
        await asyncio.gather(self._drain_audio(), self._speak_script())

    async def _drain_audio(self) -> None:
        async for _ in self._input_ch:
            pass

    async def _speak_script(self) -> None:
        elapsed = 0.0
        for utterance in self._script:
            await asyncio.sleep(max(utterance.after_s - elapsed, 0.0))
            elapsed = max(utterance.after_s, elapsed)
            self._event_ch.send_nowait(speech_event(utterance))


class ScriptedMicrophone(io.AudioInput):
    """Plays a fixed line of frames into the session, then holds the line open like a caller."""

    def __init__(self, frames: Sequence[rtc.AudioFrame], label: str = "scripted-mic") -> None:
        super().__init__(label=label)
        self._frames = list(frames)
        self._index = 0

    async def __anext__(self) -> rtc.AudioFrame:
        if self._index < len(self._frames):
            self._index += 1
            await asyncio.sleep(0)
            return self._frames[self._index - 1]
        await asyncio.sleep(HOLD_S)
        raise StopAsyncIteration


def speech_event(utterance: Utterance) -> stt.SpeechEvent:
    """The `SpeechEvent` a real plugin would emit for that utterance."""
    kind = (
        stt.SpeechEventType.FINAL_TRANSCRIPT
        if utterance.final
        else stt.SpeechEventType.INTERIM_TRANSCRIPT
    )
    return stt.SpeechEvent(
        type=kind,
        alternatives=[
            stt.SpeechData(
                language=utterance.language,
                text=utterance.text,
                confidence=utterance.confidence,
            )
        ],
    )


def comfort_noise(seconds: float, level_db: float = -55.0) -> list[rtc.AudioFrame]:
    """The hiss a PSTN leg sends while nobody speaks: noise at a level, and nothing else."""
    return _frames(seconds, level_db)


def speech(seconds: float, level_db: float = -26.0) -> list[rtc.AudioFrame]:
    """Audio at conversational level — all `core.stt_gate` reads of a caller is how loud."""
    return _frames(seconds, level_db)


def _frames(seconds: float, level_db: float) -> list[rtc.AudioFrame]:
    samples = int(SAMPLE_RATE * FRAME_MS / 1000)
    amplitude = FULL_SCALE * math.pow(10.0, level_db / 20.0)
    generator = random.Random(0xA1D10)
    out = []
    for _ in range(max(int(seconds * 1000 / FRAME_MS), 0)):
        data = bytearray()
        for _ in range(samples):
            value = int(max(min(generator.gauss(0.0, amplitude), FULL_SCALE - 1), -FULL_SCALE))
            data += int(value).to_bytes(2, "little", signed=True)
        out.append(rtc.AudioFrame(bytes(data), SAMPLE_RATE, 1, samples))
    return out
