"""Making one participant deaf to another, mid-call, from the server alone.

Decisions: docs/decisions/convo.telephony.isolation.md
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
    """Stop `listener` receiving `publishers`' audio; returns the track sids actually cut."""
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
