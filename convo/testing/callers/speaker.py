"""The two ends of a call nobody is sitting at: a virtual speaker and a virtual microphone.

Decisions: docs/decisions/convo.testing.callers.speaker.md
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from livekit import rtc
from livekit.agents import tts as agent_tts
from livekit.agents.voice import io
from livekit.agents.voice.recorder_io import RecorderIO

SAMPLE_RATE = 48000
SETTLE_S = 0.5  # silence kept after the last word, so its decay is inside the file


class VirtualSpeaker(io.AudioOutput):
    """Plays the agent's audio into nothing, in real time, and says when each segment ended."""

    def __init__(self) -> None:
        super().__init__(
            label="VirtualSpeaker",
            capabilities=io.AudioOutputCapabilities(pause=False),
            sample_rate=SAMPLE_RATE,
        )
        self._pushed = 0.0
        self._started_at: float | None = None
        self._playout: asyncio.Task[None] | None = None

    async def capture_frame(self, frame: rtc.AudioFrame) -> None:
        """Take one synthesised frame; the first of a segment starts its playback clock."""
        await super().capture_frame(frame)
        if self._started_at is None:
            self._started_at = time.time()
            self.on_playback_started(created_at=self._started_at)
        self._pushed += frame.duration

    def flush(self) -> None:
        """The segment is complete: wait out what is left of it, then report it played."""
        super().flush()
        if self._started_at is not None and self._playout is None:
            self._playout = asyncio.create_task(self._play_out())

    def clear_buffer(self) -> None:
        """Barge-in: stop where we are and report the segment as interrupted."""
        if self._started_at is None:
            return
        if self._playout is not None:
            self._playout.cancel()
        self._report(position=min(self._pushed, time.time() - self._started_at), interrupted=True)

    async def _play_out(self) -> None:
        """Sleep until the audio would have finished playing, then report the segment."""
        assert self._started_at is not None
        await asyncio.sleep(max(0.0, self._started_at + self._pushed - time.time()))
        self._report(position=self._pushed, interrupted=False)

    def _report(self, *, position: float, interrupted: bool) -> None:
        self._pushed, self._started_at, self._playout = 0.0, None, None
        self.on_playback_finished(playback_position=position, interrupted=interrupted)


@dataclass
class Spoken:
    """One line the caller said: the text, the wall-clock window, and the samples that went out."""

    text: str
    started_at: float
    ended_at: float
    samples: np.ndarray
    rate: int


class VirtualMicrophone:
    """A synthetic caller's mouth: text in, real audio on a real room's wire."""

    def __init__(self, tts: agent_tts.TTS, http_session=None) -> None:
        self.tts = tts
        self.http_session = http_session
        self.source = rtc.AudioSource(tts.sample_rate, tts.num_channels)
        self.track = rtc.LocalAudioTrack.create_audio_track("caller", self.source)

    async def say(self, text: str) -> Spoken:
        """Speak one line into the room and report when it started, ended, and how it sounded."""
        started: float | None = None
        blocks: list[np.ndarray] = []
        stream = self.tts.synthesize(text)
        try:
            async for synthesized in stream:
                if started is None:
                    started = time.time()
                blocks.append(np.frombuffer(synthesized.frame.data, dtype=np.int16).copy())
                await self.source.capture_frame(synthesized.frame)
        finally:
            await stream.aclose()
        await self.source.wait_for_playout()
        now = time.time()
        samples = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.int16)
        began = started if started is not None else now
        return Spoken(text, began, now, samples, self.tts.sample_rate)

    async def publish(self, room: rtc.Room) -> None:
        """Put the microphone on the wire — the agent subscribes to this as the caller."""
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await room.local_participant.publish_track(self.track, options)

    async def aclose(self) -> None:
        """Close the source, the TTS behind it, and the HTTP session it was given."""
        await self.source.aclose()
        await self.tts.aclose()
        if self.http_session is not None:
            await self.http_session.close()


class Recording:
    """The stereo OGG of a headless call, written by the framework's own recorder."""

    def __init__(self, session, path: str | Path) -> None:
        self.session = session
        self.path = Path(path)
        self.speaker = VirtualSpeaker()
        self.recorder = RecorderIO(agent_session=session, sample_rate=SAMPLE_RATE)
        # channel 0 is the caller's: an input nobody iterates leaves it silent,
        # and the recorder refuses to start unless both channels are declared
        self.recorder.record_input(io.AudioInput(label="no microphone"))
        session.output.audio = self.recorder.record_output(self.speaker)
        # `build_session` asks for the aligned transcript only when the session also
        # listens, so a typed call would get no `tts.word` events. Turning it on here
        # is safe and local: the framework ignores the flag unless there is an audio
        # output (`voice/agent_activity.py:3465`), and this is the line that adds one.
        session.options.use_tts_aligned_transcript = True

    async def start(self) -> "Recording":
        """Open the encoder; call this before `session.start` so the greeting is in the file."""
        await self.recorder.start(output_path=self.path)
        return self

    def adopt(self) -> None:
        """Hand the session back its recorder, which `session.start` had cleared."""
        self.session._recorder_io = self.recorder

    async def aclose(self) -> None:
        """Settle, flush the last segment and close the container; the OGG is readable after."""
        await asyncio.sleep(SETTLE_S)
        await self.recorder.aclose()

    @property
    def started_at(self) -> float:
        """Wall time of sample 0 of the OGG — the origin every `t_ms` in the log counts from."""
        return self.recorder.recording_started_at or 0.0


async def open_recording(session, path: str | Path) -> Recording:
    """Wire a started-in-a-moment session for recording and open its OGG."""
    return await Recording(session, path).start()
