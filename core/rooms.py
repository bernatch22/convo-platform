"""Live rooms: what the SFU says is happening right now, as data.

The store knows what a session DID; only LiveKit knows what is on the wire
this second, and an inbound phone call never passed through `/token` — the
trunk dispatched it. So the console's "somebody is on the phone" light cannot
come from the database: it comes from `RoomService.list_rooms`, filtered to
the rooms an agent actually joined.

The server is a dependency this process does not control. Every failure —
unreachable, wrong key, no `LIVEKIT_URL` — arrives as `RoomsUnreachable` so
the door can answer 503 and the console can say "the SFU is down" instead of
"there are no calls", which is a different and much worse sentence.
"""

from typing import Any

from livekit import api
from livekit.protocol.models import ParticipantInfo

AGENT_KIND = ParticipantInfo.Kind.AGENT
SIP_KIND = ParticipantInfo.Kind.SIP
PHONE_ATTRS = ("sip.phoneNumber", "sip.trunkPhoneNumber")


class RoomsUnreachable(RuntimeError):
    """The LiveKit server could not be asked what is live."""


async def active_rooms() -> list[dict[str, Any]]:
    """Every room an agent is currently in, newest first — one call, then the socket closes."""
    client = _client()
    try:
        rooms = (await client.room.list_rooms(api.ListRoomsRequest())).rooms
        views = [await _room_view(client, room) for room in rooms]
    except Exception as error:  # noqa: BLE001 — any failure here is one 503 to the console
        raise RoomsUnreachable(f"livekit: {error}") from error
    finally:
        await client.aclose()
    live = [view for view in views if view["agent"]]
    return sorted(live, key=lambda view: view["started_at"], reverse=True)


def _client() -> api.LiveKitAPI:
    """The API client from the environment; a missing URL or key is already unreachable."""
    try:
        return api.LiveKitAPI()
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
