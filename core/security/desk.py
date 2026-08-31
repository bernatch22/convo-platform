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

`command` is the same packet carrying an ORDER rather than a fact: a steer, a
takeover or a release aimed at the room's agent, server-side. A browser does
not need it — it holds a `whisper` ticket and calls the agent's RPC directly —
but a control plane does: an escalation rule, a compliance trigger or a
`curl` from a terminal has no room connection to perform RPC over. Both roads
end at `core.security.control.SupervisorControl.apply`, which asks the same
`is_supervisor` question of the same identity.
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

# The orders this door will forward. `join` is not one: it is a fact, and `entered` writes it.
COMMANDS: tuple[str, ...] = ("steer", "takeover", "release")


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
            await _send(api_client, room, agent, {"verb": JOIN_VERB, **found})
        return {**found, "announced": agent is not None}
    finally:
        await api_client.aclose()


async def command(room: str, identity: str, verb: str, body: dict[str, Any]) -> dict[str, Any]:
    """Aim one supervision verb at a room's agent, server-side, on a supervisor's behalf.

    → `{"verb", "identity", "sent": True}` — the agent applies it and writes the
    log line; this side never hears the outcome, because the log is the outcome.

    The identity is checked against the SFU's own participant list first: a
    verb from a `sup:` who is not actually in the call is a ticket somebody
    kept, and the whole point of the short TTL is that it should not work.

    Raises `NotInRoom` when the supervisor or the agent is not there,
    `ValueError` for a verb this door does not forward, and `RoomsUnreachable`
    when the SFU cannot be asked.
    """
    if not is_supervisor(identity):
        raise NotInRoom(f"{identity!r} is not a supervisor identity")
    if verb not in COMMANDS:
        raise ValueError(f"unknown supervisor verb {verb!r}; known: {list(COMMANDS)}")
    api_client = rooms.client()
    try:
        people = await _participants(api_client, room)
        if not any(person.identity == identity for person in people):
            raise NotInRoom(f"{identity!r} is not in room {room!r}")
        agent = next((person.identity for person in people if person.kind == AGENT_KIND), None)
        if agent is None:
            raise NotInRoom(f"room {room!r} has no agent to aim {verb!r} at")
        await _send(api_client, room, agent, {"verb": verb, "identity": identity, **body})
        return {"verb": verb, "identity": identity, "sent": True}
    finally:
        await api_client.aclose()


async def _participants(api_client: api.LiveKitAPI, room: str) -> list[Any]:
    """Everyone the SFU has in this room, hidden participants included."""
    request = api.ListParticipantsRequest(room=room)
    try:
        return list((await api_client.room.list_participants(request)).participants)
    except Exception as error:  # noqa: BLE001 — one 503 to the desk, whatever went wrong
        raise rooms.RoomsUnreachable(f"livekit: {error}") from error


async def _send(api_client: api.LiveKitAPI, room: str, agent: str, body: dict[str, Any]) -> None:
    """Send one supervisor packet to the agent and nobody else — a broadcast reaches the caller."""
    request = api.SendDataRequest(
        room=room,
        data=json.dumps(body).encode("utf-8"),
        kind=rtc.DataPacketKind.KIND_RELIABLE,
        topic=TOPIC,
        destination_identities=[agent],
    )
    try:
        await api_client.room.send_data(request)
    except Exception as error:  # noqa: BLE001 — see above
        raise rooms.RoomsUnreachable(f"livekit: {error}") from error
    log.info("sent %s from %s to %s in %s", body["verb"], body.get("identity"), agent, room)
