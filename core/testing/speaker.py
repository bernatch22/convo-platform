"""Recording a headless call: a virtual speaker, and the framework's own OGG writer.

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

Open source note: nothing here knows about tenants. Hand it any `AgentSession`
with a TTS and it hands back the OGG that session would have produced.
"""

import asyncio
import time
from pathlib import Path

from livekit import rtc
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
