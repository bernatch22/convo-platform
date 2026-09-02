"""Live rooms: what the SFU says is happening right now, and the one room we ask it for.

Decisions: docs/decisions/convo.session.rooms.md
"""

import os
import uuid
from typing import Any

from livekit import api
from livekit.protocol.models import ParticipantInfo

from convo.api.auth import fleet
from convo.domain.contracts import SessionMeta

AGENT_KIND = ParticipantInfo.Kind.AGENT
SIP_KIND = ParticipantInfo.Kind.SIP
PHONE_ATTRS = ("sip.phoneNumber", "sip.trunkPhoneNumber")
EVAL_PREFIX = "eval"
PERSONA_ATTR = "eval.persona"


class RoomsUnreachable(RuntimeError):
    """The LiveKit server could not be asked what is live."""


async def active_rooms() -> list[dict[str, Any]]:
    """Every room an agent is currently in, newest first — one call, then the socket closes."""
    api_client = client()
    try:
        rooms = (await api_client.room.list_rooms(api.ListRoomsRequest())).rooms
        views = [await _room_view(api_client, room) for room in rooms]
    except Exception as error:  # noqa: BLE001 — any failure here is one 503 to the console
        raise RoomsUnreachable(f"livekit: {error}") from error
    finally:
        await api_client.aclose()
    live = [view for view in views if view["agent"]]
    return sorted(live, key=lambda view: view["started_at"], reverse=True)


async def create_eval_room(meta: SessionMeta, persona: str | None = None) -> str:
    """A fresh room the fleet's agent is ALREADY dispatched into — returns its name."""
    room = f"{EVAL_PREFIX}-{meta.tenant}-{meta.project}-{uuid.uuid4().hex[:8]}"
    request = api.CreateAgentDispatchRequest(
        room=room,
        agent_name=fleet(),
        metadata=meta.model_dump_json(),
        attributes={PERSONA_ATTR: persona} if persona else {},
    )
    api_client = client()
    try:
        await api_client.agent_dispatch.create_dispatch(request)
    except Exception as error:  # noqa: BLE001 — any failure here is one 503 to the caller
        raise RoomsUnreachable(f"livekit: {error}") from error
    finally:
        await api_client.aclose()
    return room


def client() -> api.LiveKitAPI:
    """The API client, on the same defaults `core.auth` mints tokens with."""
    try:
        return api.LiveKitAPI(
            url=os.getenv("LIVEKIT_URL", "ws://localhost:7880"),
            api_key=os.getenv("LIVEKIT_API_KEY", "devkey"),
            api_secret=os.getenv("LIVEKIT_API_SECRET", "secret"),
        )
    except ValueError as error:
        raise RoomsUnreachable(f"livekit is not configured: {error}") from error


async def _room_view(client: api.LiveKitAPI, room) -> dict[str, Any]:
    """One room with its participants: is the agent in, and is a phone on the other end."""
    request = api.ListParticipantsRequest(room=room.name)
    people = (await client.room.list_participants(request)).participants
    return {
        "room": room.name,
        "sid": room.sid,
        "participants": room.num_participants,
        "started_at": float(room.creation_time),
        "agent": any(person.kind == AGENT_KIND for person in people),
        "identities": [person.identity for person in people],
        "phone": _phone(people),
    }


def _phone(people) -> str | None:
    """The caller's number when the room holds a SIP participant, else None (a web caller)."""
    for person in people:
        if person.kind != SIP_KIND:
            continue
        for attribute in PHONE_ATTRS:
            if person.attributes.get(attribute):
                return person.attributes[attribute]
    return None
