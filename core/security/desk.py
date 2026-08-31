"""The control plane's side of supervision: confirm the human is really there, then tell the agent.

`mint_supervisor` hands out a ticket; a ticket is an intention, not a
presence. What belongs in a compliance log is the arrival — so the desk asks
the SFU who is actually in the room before it writes anything down, and reads
the capability off the SFU's own copy of the signed token
(`attributes["cap"]`, put there by `core.auth.mint_supervisor`) rather than
off anything the browser sends. A client that lies about its capability is
lying to a field nobody reads.

The announcement goes to the **agent alone**. Broadcasting it would deliver a
data packet saying "a supervisor joined" straight into the caller's browser,
which is the one thing this whole feature exists not to do — so the
destination is the room's agent participant, by identity, and a room with no
agent in it is announced to nobody.

Why an announcement at all: measured on this box (livekit-server v1.9.1), a
hidden participant fires no `participant_connected` anywhere, so the agent
cannot see the arrival even if it wanted to. The control plane can — it holds
the API key — and the packet is how the fact reaches the process that owns the
caller's log, where the `seq` is allocated. One writer, one sequence, one story.
"""

import json
import logging
from typing import Any

from livekit import api, rtc

from core import rooms
from core.security.monitor import JOIN_VERB, TOPIC
from core.security.supervisor import is_supervisor

log = logging.getLogger("platform.supervisor")

AGENT_KIND = rooms.AGENT_KIND
DEFAULT_CAPABILITY = "listen"


class NotInRoom(LookupError):
    """The SFU has no such participant in that room: there is no arrival to record."""


async def entered(room: str, identity: str) -> dict[str, Any]:
    """Confirm a supervisor is in this room, tell its agent, and report what the SFU sees.

    → `{"identity", "capability", "hidden", "announced"}`

    `hidden` is the SFU's answer, not ours — it is the honest way to show a
    supervisor that the caller genuinely cannot see them, and it is what the
    desk puts on screen. `announced` is False when the room holds no agent to
    tell, which is not an error: the call has no log being written either.

    Raises `NotInRoom` when the identity is not in the room (a ticket that was
    minted and never used), and `RoomsUnreachable` when the SFU cannot be asked.
    """
    if not is_supervisor(identity):
        raise NotInRoom(f"{identity!r} is not a supervisor identity")
    api_client = rooms.client()
    try:
        people = await _participants(api_client, room)
        seen = next((person for person in people if person.identity == identity), None)
        if seen is None:
            raise NotInRoom(f"{identity!r} is not in room {room!r}")
        found = {
            "identity": identity,
            "capability": dict(seen.attributes).get("cap", DEFAULT_CAPABILITY),
            "hidden": bool(seen.permission.hidden),
        }
        agent = next((person.identity for person in people if person.kind == AGENT_KIND), None)
        if agent is not None:
            await _announce(api_client, room, agent, found)
        return {**found, "announced": agent is not None}
    finally:
        await api_client.aclose()


async def _participants(api_client: api.LiveKitAPI, room: str) -> list[Any]:
    """Everyone the SFU has in this room, hidden participants included."""
    request = api.ListParticipantsRequest(room=room)
    try:
        return list((await api_client.room.list_participants(request)).participants)
    except Exception as error:  # noqa: BLE001 — one 503 to the desk, whatever went wrong
        raise rooms.RoomsUnreachable(f"livekit: {error}") from error


async def _announce(
    api_client: api.LiveKitAPI, room: str, agent: str, found: dict[str, Any]
) -> None:
    """Send the join to the agent and nobody else — a broadcast would reach the caller."""
    request = api.SendDataRequest(
        room=room,
        data=json.dumps({"verb": JOIN_VERB, **found}).encode("utf-8"),
        kind=rtc.DataPacketKind.KIND_RELIABLE,
        topic=TOPIC,
        destination_identities=[agent],
    )
    try:
        await api_client.room.send_data(request)
    except Exception as error:  # noqa: BLE001 — see above
        raise rooms.RoomsUnreachable(f"livekit: {error}") from error
    log.info("announced %s to %s in %s", found["identity"], agent, room)
