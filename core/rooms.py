"""Live rooms: what the SFU says is happening right now, and the one room we ask it for.

The store knows what a session DID; only LiveKit knows what is on the wire
this second, and an inbound phone call never passed through `/token` — the
trunk dispatched it. So the console's "somebody is on the phone" light cannot
come from the database: it comes from `RoomService.list_rooms`, filtered to
the rooms an agent actually joined.

The server is a dependency this process does not control. Every failure —
unreachable, wrong key, no `LIVEKIT_URL` — arrives as `RoomsUnreachable` so
the door can answer 503 and the console can say "the SFU is down" instead of
"there are no calls", which is a different and much worse sentence.

`create_eval_room` is the write side, and the only one: a room dispatched
server-side, with metadata, for a caller that cannot carry any — see its
docstring for why that caller exists.
"""

import os
import uuid
from typing import Any

from livekit import api
from livekit.protocol.models import ParticipantInfo

from core.auth import fleet
from core.contracts import SessionMeta

AGENT_KIND = ParticipantInfo.Kind.AGENT
SIP_KIND = ParticipantInfo.Kind.SIP
PHONE_ATTRS = ("sip.phoneNumber", "sip.trunkPhoneNumber")
EVAL_PREFIX = "eval"
PERSONA_ATTR = "eval.persona"


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


async def create_eval_room(meta: SessionMeta, persona: str | None = None) -> str:
    """A fresh room the fleet's agent is ALREADY dispatched into — returns its name.

    The one door ring 2 enters through, and the reason it exists is a
    limitation nobody can code around: DeepEval's `LiveKitConnector` signs its
    own join token and dispatches with `RoomAgentDispatch(agent_name=…)` and
    **no metadata** (`voice/connectors/providers/livekit.py:179`), so a room it
    opens on its own reaches an agent that cannot tell which tenant called.
    Dispatching from here instead puts the same `SessionMeta` JSON a web token
    carries into `ctx.job.metadata`, where `core.router.resolve` already reads
    it — the harness then joins a room whose agent is already on its way.

    The name is prefixed `eval-` so a synthetic call is one glance apart from a
    real one in `/live-calls` and in the SFU's own logs. `persona`, when the
    caller names one, rides on the dispatch attributes as `eval.persona`: the
    worker's job then says which persona is calling it.

    Explicit dispatch creates the room if it does not exist, so this is one
    round-trip, not two.
    """
    room = f"{EVAL_PREFIX}-{meta.tenant}-{meta.project}-{uuid.uuid4().hex[:8]}"
    request = api.CreateAgentDispatchRequest(
        room=room,
        agent_name=fleet(),
        metadata=meta.model_dump_json(),
        attributes={PERSONA_ATTR: persona} if persona else {},
    )
    client = _client()
    try:
        await client.agent_dispatch.create_dispatch(request)
    except Exception as error:  # noqa: BLE001 — any failure here is one 503 to the caller
        raise RoomsUnreachable(f"livekit: {error}") from error
    finally:
        await client.aclose()
    return room


def _client() -> api.LiveKitAPI:
    """The API client, on the same defaults `core.auth` mints tokens with.

    `api.LiveKitAPI()` reads the environment itself and raises when `LIVEKIT_URL`
    is unset — which on a laptop running the dev compose is not "unconfigured",
    it is "the defaults". `core.auth.mint_session` has always fallen back to
    `ws://localhost:7880` + devkey/secret, and a console that can hand out a
    token for a room it then cannot list is the wrong kind of surprising. A key
    that is wrong for the server still arrives as `RoomsUnreachable`.
    """
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
