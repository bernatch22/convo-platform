"""The two ends of a call nobody is sitting at: a virtual speaker and a virtual microphone.

A real `--record` run needs a microphone and a room. `RecorderIO` — the thing
that writes the stereo OGG — is only wired by `AgentSession.start` when there
is a job context AND both an audio input and an audio output, which a headless
harness session has neither of. So this file supplies the missing half:

  `VirtualSpeaker`  an `AudioOutput` that "plays" the TTS at wall-clock speed
                    and reports each segment where it finished, so the recorder
                    places the agent's words on the real timeline
  `Recording`       the framework's `RecorderIO`, wired by hand around that
                    speaker and started before the session is

The caller's channel stays SILENT on purpose: no microphone was ever attached
and `record_input` is given an input nobody iterates. The OGG is therefore a
truthful stereo file — L = caller (silence), R = agent — of a call in which the
caller typed. What that costs each voice metric is written down in
`docs/evals.md` §3.9.

`VirtualMicrophone` is the other end, and the one ring 2 needs: a synthetic
caller in a REAL room has to put sound on the wire, so it speaks its line with
a TTS of its own and reports the wall-clock window that line occupied. The two
classes never meet — one is an `AgentSession`'s output, the other a
`rtc.Room`'s input — but they are the same idea twice and belong together.

Open source note: nothing here knows about tenants. Hand `Recording` any
`AgentSession` with a TTS and it hands back the OGG that session would have
produced; hand `VirtualMicrophone` any livekit-agents TTS and it is a headless
caller's mouth in any LiveKit room.
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
    """Plays the agent's audio into nothing, in real time, and says when each segment ended.

    Frames arrive from the TTS far faster than they are spoken. A sink that
    accepted them and reported "finished" immediately would collapse a
    forty-second call into two seconds of OGG and give every turn a latency it
    never had, so this one sleeps out the audio it was handed before reporting.
    """

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
    """A synthetic caller's mouth: text in, real audio on a real room's wire.

    The pacing is the SFU's, not ours. `AudioSource.capture_frame` blocks once
    its queue is full and `wait_for_playout` returns when the queue has
    drained, so pushing every synthesised frame and then waiting takes the same
    wall-clock time the sentence takes to say. That matters twice: the agent's
    VAD must see the real gap after the line, and the window `say` reports is
    what gives the caller's turn an `Audio.start_time` that is true.

    The samples are kept as they go out, because a scored turn needs the SOUND
    of what the caller said and no track carries our own voice back to us.

    `http_session` is not optional plumbing. A livekit-agents plugin asks the
    framework's job context for its HTTP session, and a harness that is not a
    job has none: without one handed in, the first `say` dies with "Attempted
    to use an http session outside of a job context". Whoever passes it owns
    nothing — this closes it.
    """

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
    """The stereo OGG of a headless call, written by the framework's own recorder.

    Three moments, because `AgentSession.start` clears `_recorder_io` on its way
    through: wire the output BEFORE the session starts (or the greeting is
    spoken into a sink nobody is recording), `adopt` the recorder after it
    started so `session.end` can report where the audio went, and `aclose` it
    before the session closes so the file is complete.
    """

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
        """Settle, flush the last segment and close the container; the OGG is readable after.

        The writer only fills the timeline up to `now`, and `now` at close is
        the instant the last frame finished playing — which cuts the decay off
        the final word and reads to `AudioIntegrityMetric` as an abrupt cutoff.
        A beat of silence first is what a real line has anyway.
        """
        await asyncio.sleep(SETTLE_S)
        await self.recorder.aclose()

    @property
    def started_at(self) -> float:
        """Wall time of sample 0 of the OGG — the origin every `t_ms` in the log counts from."""
        return self.recorder.recording_started_at or 0.0


async def open_recording(session, path: str | Path) -> Recording:
    """Wire a started-in-a-moment session for recording and open its OGG."""
    return await Recording(session, path).start()
