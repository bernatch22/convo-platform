"""Making one participant deaf to another, mid-call, from the server alone.

A warm transfer is a briefing the caller must not hear. Everything else about
it — dialling the human, bridging the three of them — is easy; that one
sentence is the whole difficulty, because the human arrives as a SIP
participant created by `livekit-sip` and we have no client code running on
their side to ask them to be quiet.

So the cut has to be server-side, and it has to hold against a subscriber that
joined with `autoSubscribe`. **Measured on this box** (livekit-server v1.9.1,
`scripts/isolation_probe.py`, three RTC peers publishing a continuous tone and
counting the frames each one actually receives):

```
P0 baseline                       caller <- agent 400   caller <- human 400
P1 update_subscriptions(False)    caller <- agent   0   caller <- human   0
P2 update_subscriptions(True)     caller <- agent 400   caller <- human 400
P3 set_track_subscription_perms   caller <- agent   0   caller <- human   0
P4 permissions re-opened          caller <- agent 400   caller <- human 400
```

Both cut the audio completely. **Neither cuts it instantly**: the same probe
measures the switch taking about **220 ms per stream** to bite, which is not a
rounding error — it is a fifth of a second of a briefing, and it is why
`WarmLeg.dial` documents a residual rather than claiming silence.

Both mechanisms work, and the counters are the reason this file trusts them:
an earlier probe watched `track_subscribed` / `track_unsubscribed` on the
subscriber's own client and concluded that NEITHER worked — the SFU log said
`revoking subscription` at the same moment. The Python SDK does not fire
`track_unsubscribed` for a server-side revocation; the `AudioStream` simply
goes quiet. Watching events would have shipped the wrong answer.

`update_subscriptions` is the one used here, because it needs nothing of the
participant being cut off — which is the whole problem: the colleague on the
warm leg is a SIP participant with no client of ours to ask.
`set_track_subscription_permissions` is the publisher's own call and would work
for the agent's track but not for the colleague's, and one mechanism for both
directions is one thing to reason about.

Open source note: reusable as-is. "Two participants confer while a third
waits" is the shape of every warm handoff, every side-channel and every
break-out room, and on a self-hosted SFU this is how it is done.
"""

import logging
from collections.abc import Iterable
from typing import Any

from livekit import api

log = logging.getLogger("platform.telephony")


async def published(client: api.LiveKitAPI, room: str) -> dict[str, list[str]]:
    """Every participant's published track sids in one room, by identity."""
    request = api.ListParticipantsRequest(room=room)
    people = (await client.room.list_participants(request)).participants
    return {person.identity: [track.sid for track in person.tracks] for person in people}


async def cut(
    client: api.LiveKitAPI, room: str, listener: str, publishers: Iterable[str]
) -> list[str]:
    """Stop `listener` receiving `publishers`' audio; returns the track sids actually cut.

    An empty list means there was nothing published to cut — a human whose
    phone has not answered yet, or a participant already gone. It is not an
    error and it is not silence: the caller would still hear them.
    """
    tracks = await published(client, room)
    sids = [sid for who in publishers for sid in tracks.get(who, ())]
    if not sids:
        return []
    await _subscribe(client, room, listener, sids, on=False)
    log.info("%s can no longer hear %s in %s", listener, list(publishers), room)
    return sids


async def restore(client: api.LiveKitAPI, room: str, listener: str, sids: list[str]) -> None:
    """Let `listener` hear those tracks again — the bridge at the end of a warm transfer."""
    if not sids:
        return
    await _subscribe(client, room, listener, sids, on=True)
    log.info("%s hears %d track(s) again in %s", listener, len(sids), room)


def peers(room: Any) -> dict[str, Any]:
    """The remote participants of an `rtc.Room` as a plain dict; `{}` when there is no room."""
    return dict(getattr(room, "remote_participants", None) or {})


async def _subscribe(
    client: api.LiveKitAPI, room: str, listener: str, sids: list[str], on: bool
) -> None:
    request = api.UpdateSubscriptionsRequest(
        room=room, identity=listener, track_sids=sids, subscribe=on
    )
    await client.room.update_subscriptions(request)
