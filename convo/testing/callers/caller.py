"""The synthetic caller itself: one participant in one room, speaking and listening.

Decisions: docs/decisions/convo.testing.callers.caller.md
"""

import asyncio
import time
from dataclasses import dataclass

import numpy as np
from deepeval.test_case import Turn
from livekit import rtc

from convo.testing.callers.audio import Timeline, audio_clip
from convo.testing.callers.speaker import Spoken, VirtualMicrophone

TRANSCRIPTION_TOPIC = "lk.transcription"
SEGMENT_ID_ATTR = "lk.segment_id"
AGENT_STATE_ATTR = "lk.agent.state"
AGENT_KIND = rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
AGENT_RATE = 48000
JOIN_TIMEOUT_S = 30.0
REPLY_TIMEOUT_S = 60.0
QUIET_AFTER_REPLY_S = 3.0  # a turn that calls a tool speaks twice; both halves are one reply
FLOOR_POLL_S = 0.02  # `lk.agent.state` is an attribute, not a stream: it is watched by looking
TAIL_GRACE_S = 2.0  # how long the text of an answer we cut off may take to arrive


@dataclass
class Segment:
    """One settled transcription segment: whose it is, what it says, when it arrived."""

    id: str
    identity: str
    text: str
    at: float


class Call:
    """One synthetic call: join a minted room, speak, hear the answer, hang up."""

    def __init__(self, ticket: dict[str, str], mic: VirtualMicrophone) -> None:
        self.ticket = ticket
        self.mic = mic
        self.room = rtc.Room()
        self.identity = ticket.get("identity", "caller")
        self.origin = time.time()
        self.heard = Timeline(AGENT_RATE, origin=self.origin)
        self.states: list[tuple[str, float]] = []
        self.inbox: asyncio.Queue[Segment] = asyncio.Queue()
        self.ours: dict[str, str] = {}
        self._agent_ready = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()

    async def join(self) -> None:
        """Connect, publish the microphone and wait until the agent's voice is subscribed."""
        self.room.register_text_stream_handler(TRANSCRIPTION_TOPIC, self._on_text)
        self.room.on("participant_attributes_changed", self._on_attributes)
        self.room.on("track_subscribed", self._on_track)
        self.origin = self.heard.origin = time.time()
        await self.room.connect(self.ticket["url"], self.ticket["token"])
        await self.mic.publish(self.room)
        try:
            await asyncio.wait_for(self._agent_ready.wait(), JOIN_TIMEOUT_S)
        except TimeoutError as error:
            raise TimeoutError(
                f"no agent published audio in room {self.ticket['room']!r} within "
                f"{JOIN_TIMEOUT_S:.0f}s — is `python worker.py dev` running against "
                "this LiveKit server, and is FLEET the name the dispatch used?"
            ) from error

    async def say(self, line: str) -> Spoken:
        """Speak one line out loud, in real time, and report the window it occupied."""
        self.ours.clear()
        return await self.mic.say(line)

    async def listen(self, since: float, patience: float | None = None) -> Turn:
        """The agent's answer, whole, or as much of it as this caller will sit through."""
        if patience is not None:
            return await self._cut_in(since, patience)
        return await self._hear_out(since)

    async def settle(self, turn: Turn, grace: float = TAIL_GRACE_S) -> Turn:
        """Fold the tail of an answer we cut off into the turn it was cut from, in place."""
        if not turn.interrupted:
            return turn
        tail = await self._next_segment(grace)
        if tail is not None:
            turn.content = " ".join(part for part in (turn.content, tail.text) if part)
        return turn

    async def _hear_out(self, since: float) -> Turn:
        """Every segment until the agent goes quiet AND stops speaking, and the audio of it."""
        opening = await self._next_segment(REPLY_TIMEOUT_S)
        if opening is None:
            raise TimeoutError(
                f"the agent said nothing for {REPLY_TIMEOUT_S:.0f}s in room "
                f"{self.ticket['room']!r} — check the worker's log for a provider error"
            )
        segments = {opening.id: opening.text}
        patience = time.time() + REPLY_TIMEOUT_S  # an agent stuck on `speaking` still ends the turn
        while time.time() < patience:
            more = await self._next_segment(QUIET_AFTER_REPLY_S)
            if more is not None:
                segments[more.id] = more.text
            elif not self._holding_the_floor():
                break
        until = time.time()
        window = self._spoke_between(since, until)
        started = window[0] if window else opening.at
        return Turn(
            role="assistant",
            content=" ".join(segments.values()),
            audio=self.heard.audio(*window) if window else None,
            latency_ms=round((started - since) * 1000, 1),
            interrupted=self._holding_the_floor(),
        )

    async def _cut_in(self, since: float, patience: float) -> Turn:
        """Listen for `patience` seconds of the agent's speech, then hand the floor back."""
        floor = await self._floor_taken(since, REPLY_TIMEOUT_S)
        if floor is None:
            raise TimeoutError(
                f"the agent never took the floor in {REPLY_TIMEOUT_S:.0f}s in room "
                f"{self.ticket['room']!r} — check the worker's log for a provider error"
            )
        segments: dict[str, str] = {}
        while (left := floor + patience - time.time()) > 0:
            more = await self._next_segment(left)
            if more is None:
                break
            segments[more.id] = more.text
        return Turn(
            role="assistant",
            content=" ".join(segments.values()),
            audio=self.heard.audio(floor, time.time()),
            latency_ms=round((floor - since) * 1000, 1),
            interrupted=self._holding_the_floor(),
        )

    def heard_us(self, spoken: Spoken) -> Turn:
        """The caller's turn: what the agent's STT made of the line, with the audio we sent."""
        return Turn(
            role="user",
            content=" ".join(self.ours.values()) or spoken.text,
            audio=audio_clip(spoken.samples, spoken.rate, spoken.started_at - self.origin),
            metadata={"said": spoken.text},
        )

    async def hang_up(self) -> None:
        """Leave the room and close the microphone; the session ends when we do."""
        for task in list(self._tasks):
            task.cancel()
        await self.room.disconnect()
        await self.mic.aclose()

    async def _next_segment(self, timeout: float) -> Segment | None:
        """The agent's next settled segment, or None when the line stays quiet that long."""
        try:
            return await asyncio.wait_for(self.inbox.get(), timeout)
        except TimeoutError:
            return None

    def _spoke_between(self, since: float, until: float) -> tuple[float, float] | None:
        """When the agent held the floor between two moments, off its own `lk.agent.state`."""
        taken = self._floor_after(since)
        if taken is None:
            return None
        released = [at for state, at in self.states if state != "speaking" and at > taken]
        return taken, (released[-1] if released else until)

    async def _floor_taken(self, since: float, timeout: float) -> float | None:
        """Wait until the agent takes the floor after `since`, and say when it did."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            taken = self._floor_after(since)
            if taken is not None:
                return taken
            await asyncio.sleep(FLOOR_POLL_S)
        return None

    def _floor_after(self, since: float) -> float | None:
        """The first moment the agent started speaking after `since`, if it has."""
        taken = [at for state, at in self.states if state == "speaking" and at >= since]
        return taken[0] if taken else None

    def _holding_the_floor(self) -> bool:
        """Is the agent speaking right now? What makes an interruption an interruption."""
        return bool(self.states) and self.states[-1][0] == "speaking"

    def _on_text(self, reader: rtc.TextStreamReader, identity: str) -> None:
        """One transcription stream is opening; read it to its end off the event loop."""
        self._spawn(self._settle(reader, identity))

    async def _settle(self, reader: rtc.TextStreamReader, identity: str) -> None:
        """Read a segment whole, then file it under whoever it belongs to."""
        attributes = reader.info.attributes or {}
        segment = Segment(
            id=attributes.get(SEGMENT_ID_ATTR) or reader.info.id,
            identity=identity,
            text=(await reader.read_all()).strip(),
            at=time.time(),
        )
        if not segment.text:
            return
        if segment.identity == self.identity:
            self.ours[segment.id] = segment.text  # a later stream with this id replaces it
        else:
            await self.inbox.put(segment)

    def _on_attributes(self, changed: dict[str, str], participant) -> None:
        """Remember every `lk.agent.state` change: `speaking` is when sound leaves for us."""
        if AGENT_STATE_ATTR in changed and participant.kind == AGENT_KIND:
            self.states.append((changed[AGENT_STATE_ATTR], time.time()))

    def _on_track(self, track: rtc.Track, publication, participant) -> None:
        """Subscribe to the agent's voice and start writing it onto this call's timeline."""
        if track.kind != rtc.TrackKind.KIND_AUDIO or participant.kind != AGENT_KIND:
            return
        self._spawn(self._drain(rtc.AudioStream(track, sample_rate=AGENT_RATE, num_channels=1)))
        self._agent_ready.set()

    async def _drain(self, stream: rtc.AudioStream) -> None:
        """Every frame the agent sent, placed at the wall clock its audio began."""
        async for event in stream:
            samples = np.frombuffer(event.frame.data, dtype=np.int16)
            self.heard.add(samples, at=time.time() - event.frame.duration)

    def _spawn(self, coro) -> None:
        """Hold every background task: one nobody holds is one the GC may cancel."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
