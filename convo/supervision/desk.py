"""The control plane's side of supervision: confirm the human is really there, then tell the agent.

Decisions: docs/decisions/convo.supervision.desk.md
"""

import json
import logging
from typing import Any

from livekit import api, rtc

from convo.session import rooms
from convo.supervision.monitor import JOIN_VERB, TOPIC
from convo.supervision.supervisor import is_supervisor

log = logging.getLogger("platform.supervisor")

AGENT_KIND = rooms.AGENT_KIND
DEFAULT_CAPABILITY = "listen"

# The orders this door will forward. `join` is not one: it is a fact, and `entered` writes it.
COMMANDS: tuple[str, ...] = ("steer", "takeover", "release", "transfer")


class NotInRoom(LookupError):
    """The SFU has no such participant in that room: there is no arrival to record."""


async def entered(room: str, identity: str) -> dict[str, Any]:
    """Confirm a supervisor is in this room, tell its agent, and report what the SFU sees."""
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
    """Aim one supervision verb at a room's agent, server-side, on a supervisor's behalf."""
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
