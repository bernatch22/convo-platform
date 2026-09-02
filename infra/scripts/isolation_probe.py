"""isolation_probe.py — can this SFU keep a briefing from the caller? Measured in audio frames.

Decisions: docs/decisions/infra.scripts.isolation_probe.md
"""

import argparse
import asyncio
import os
import sys

import numpy as np
from livekit import api, rtc

ROOM = "probe-isolation"
RATE = 48000
CHUNK = 480  # 10 ms of samples, the frame size the SFU is fed
TONE_HZ = 440
HEARD = 5  # frames in a phase below which a pair counts as silent
SETTLE_S = 1.0  # how long a switch is given to bite before the phase is measured


def main(argv: list[str]) -> int:
    """Run the five phases and print a table an operator can read at a glance."""
    args = parse_args(argv)
    asyncio.run(probe(args.phase))
    return 0


async def probe(phase_s: float) -> None:
    """Three peers, two mechanisms, five phases — and the counters between each."""
    peers = [Peer("agent"), Peer("caller"), Peer("human")]
    agent, _caller, human = peers
    watched = [("caller", "agent"), ("caller", "human"), ("agent", "human"), ("human", "agent")]
    client = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL", "ws://localhost:7880"),
        api_key=os.getenv("LIVEKIT_API_KEY", "devkey"),
        api_secret=os.getenv("LIVEKIT_API_SECRET", "secret"),
    )
    try:
        for peer in peers:
            await peer.join()
        await asyncio.sleep(phase_s)
        sids = await track_sids(client)

        await measure(peers, watched, phase_s, "P0 baseline — everybody hears everybody")

        await settle(peers, lambda: subscribe(client, sids, on=False))
        await measure(peers, watched, phase_s, "P1 server-side UpdateSubscriptions(False)")

        await settle(peers, lambda: subscribe(client, sids, on=True))
        await measure(peers, watched, phase_s, "P2 the same call undone")

        await settle(peers, lambda: permissions(agent, human, open_to_all=False))
        briefing = "P3 BRIEFING — agent and human allow only each other"
        await measure(peers, watched, phase_s, briefing)

        await settle(peers, lambda: permissions(agent, human, open_to_all=True))
        await measure(peers, watched, phase_s, "P4 BRIDGED — permissions re-opened")
    finally:
        for peer in peers:
            await peer.leave()
        await client.aclose()


class Peer:
    """One participant that publishes a tone and counts what it receives from each other one."""

    def __init__(self, identity: str) -> None:
        self.identity = identity
        self.room = rtc.Room()
        self.frames: dict[str, int] = {}
        self.tasks: list[asyncio.Task] = []
        self.room.on("track_subscribed", self._on_subscribed)

    async def join(self) -> None:
        """Connect, publish a microphone track, and start counting."""
        await self.room.connect(_url(), token(self.identity), rtc.RoomOptions(auto_subscribe=True))
        self.source = rtc.AudioSource(RATE, 1)
        track = rtc.LocalAudioTrack.create_audio_track(f"{self.identity}-mic", self.source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await self.room.local_participant.publish_track(track, options)
        self.tasks.append(asyncio.create_task(self._tone()))

    async def leave(self) -> None:
        """Stop every task and disconnect; a probe that leaves peers behind blocks the next run."""
        for task in self.tasks:
            task.cancel()
        try:
            await self.room.disconnect()
        except Exception as error:  # noqa: BLE001 — a probe's teardown is not its result
            print(f"{self.identity}: disconnect failed: {error}", file=sys.stderr)

    def _on_subscribed(self, track, publication, participant) -> None:
        self.tasks.append(asyncio.create_task(self._count(track, participant.identity)))

    async def _count(self, track, who: str) -> None:
        async for _frame in rtc.AudioStream(track):
            self.frames[who] = self.frames.get(who, 0) + 1

    async def _tone(self) -> None:
        sample = 0
        while True:
            samples = np.arange(sample, sample + CHUNK)
            wave = (np.sin(2 * np.pi * TONE_HZ * samples / RATE) * 12000).astype(np.int16)
            await self.source.capture_frame(rtc.AudioFrame(wave.tobytes(), RATE, 1, CHUNK))
            sample += CHUNK


async def measure(
    peers: list[Peer], watched: list[tuple[str, str]], phase_s: float, title: str
) -> None:
    """Print how many frames moved on each watched pair over one phase."""
    print(f"\n{title}")
    before = {(p.identity, who): n for p in peers for who, n in p.frames.items()}
    await asyncio.sleep(phase_s)
    after = {(p.identity, who): n for p in peers for who, n in p.frames.items()}
    for listener, publisher in watched:
        moved = after.get((listener, publisher), 0) - before.get((listener, publisher), 0)
        verdict = "HEARS" if moved > HEARD else "silent"
        print(f"    {listener:<7} <- {publisher:<7} {moved:>5} frames   {verdict}")


async def track_sids(client: api.LiveKitAPI) -> dict[str, str]:
    """Each participant's first published track, by identity — what UpdateSubscriptions names."""
    request = api.ListParticipantsRequest(room=ROOM)
    people = (await client.room.list_participants(request)).participants
    return {person.identity: person.tracks[0].sid for person in people if person.tracks}


async def settle(peers: list[Peer], switch) -> None:
    """Throw the switch and say how much audio still reached the caller before it bit."""
    caller = next(peer for peer in peers if peer.identity == "caller")
    before = dict(caller.frames)
    await switch()
    await asyncio.sleep(SETTLE_S)
    leaked = sum(caller.frames.get(who, 0) - before.get(who, 0) for who in ("agent", "human"))
    print(f"\n    settling ({SETTLE_S:.1f}s): {leaked} frame(s) still reached the caller")


async def subscribe(client: api.LiveKitAPI, sids: dict[str, str], on: bool) -> None:
    """Switch the caller's subscription to the agent and the human, server-side."""
    request = api.UpdateSubscriptionsRequest(
        room=ROOM, identity="caller", track_sids=[sids["agent"], sids["human"]], subscribe=on
    )
    await client.room.update_subscriptions(request)


async def permissions(agent: Peer, human: Peer, open_to_all: bool) -> None:
    """The publisher's own gate: either everybody may subscribe, or only the other one."""
    for peer, only in ((agent, "human"), (human, "agent")):
        peer.room.local_participant.set_track_subscription_permissions(
            allow_all_participants=open_to_all,
            participant_permissions=[]
            if open_to_all
            else [rtc.ParticipantTrackPermission(participant_identity=only, allow_all=True)],
        )


def token(identity: str) -> str:
    """A join token for the probe room; the dev compose's default key signs it."""
    grants = api.VideoGrants(room_join=True, room=ROOM, can_publish=True, can_subscribe=True)
    return (
        api.AccessToken(
            os.getenv("LIVEKIT_API_KEY", "devkey"), os.getenv("LIVEKIT_API_SECRET", "secret")
        )
        .with_identity(identity)
        .with_grants(grants)
        .to_jwt()
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    """`--phase` is the only knob: how many seconds each measurement runs for."""
    parser = argparse.ArgumentParser(description="Measure audio isolation on a LiveKit server.")
    parser.add_argument("--phase", type=float, default=4.0, help="seconds per phase (default 4)")
    return parser.parse_args(argv)


def _url() -> str:
    return os.getenv("LIVEKIT_URL", "ws://localhost:7880")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
