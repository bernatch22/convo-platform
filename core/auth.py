"""Session tokens: one caller's ticket into one new room, with the agent dispatched to it.

Tenant isolation lives in this module, not in the SFU: a LiveKit API key can
sign for any room, so the exact-string room grant minted here is the fence.
The JWT also carries `RoomAgentDispatch(agent_name=FLEET, metadata=SessionMeta)`
— the same JSON `core.router.resolve` reads — so who a session is for is
decided once, at the door, and travels with the room.

`mint_observer` is the second ticket this module signs: the same fence, with
the publish rights removed, so a supervisor can listen to a call in progress
without the caller ever learning that somebody joined. `mint_caller` is the
third: full publish rights into a room that already dispatches its own agent,
which is how a synthetic caller (ring 2) gets in.

Open source note: `mint_session` is a generic recipe for explicit agent
dispatch on livekit-agents 1.7 — a JWT from plain args, no server round-trip.
"""

import os
import uuid

from livekit import api

from core.contracts import SessionMeta


def mint_session(meta: SessionMeta, user_id: str = "anonymous") -> dict[str, str]:
    """Mint {url, room, token} for one session: a fresh room, joinable by exactly this caller."""
    room = f"{meta.tenant}-{meta.project}-{uuid.uuid4().hex[:8]}"
    grants = api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True)
    dispatch = api.RoomAgentDispatch(agent_name=fleet(), metadata=meta.model_dump_json())
    token = (
        api.AccessToken(os.getenv("LIVEKIT_API_KEY", "devkey"), _secret())
        .with_identity(f"{meta.tenant}:{user_id}")
        .with_attributes({"tenant": meta.tenant, "role": "customer"})
        .with_grants(grants)
        .with_room_config(api.RoomConfiguration(agents=[dispatch]))
        .to_jwt()
    )
    return {"url": os.getenv("LIVEKIT_URL", "ws://localhost:7880"), "room": room, "token": token}


def mint_observer(room: str) -> dict[str, str]:
    """A listen-only ticket into ONE existing room: subscribe, never publish, never appear.

    This is how a supervisor listens to a call that is already happening. The
    grant is the opposite of a caller's: `can_publish=False` means no
    microphone can reach the room from this token however the browser is
    driven, and `hidden=True` keeps the observer out of the room's participant
    list, so the caller is not told somebody joined. It carries no
    `RoomConfiguration`: an observer never dispatches an agent, it joins a room
    an agent is already in.
    """
    identity = f"observer:{uuid.uuid4().hex[:8]}"
    grants = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=False,
        can_publish_data=False,
        can_subscribe=True,
        hidden=True,
    )
    token = (
        api.AccessToken(os.getenv("LIVEKIT_API_KEY", "devkey"), _secret())
        .with_identity(identity)
        .with_attributes({"role": "observer"})
        .with_grants(grants)
        .to_jwt()
    )
    return {
        "url": os.getenv("LIVEKIT_URL", "ws://localhost:7880"),
        "room": room,
        "identity": identity,
        "token": token,
    }


def mint_caller(room: str, tenant: str, identity: str = "caller") -> dict[str, str]:
    """A speaking ticket into ONE room that ALREADY has its agent dispatched.

    The third ticket, and the one an eval harness needs. `mint_session` puts
    the dispatch inside the JWT, which only works for a client that joins with
    the token we minted; DeepEval's `LiveKitConnector` signs its own token and
    cannot carry metadata, so an eval room is dispatched server-side
    (`core.rooms.create_eval_room`) and the caller is handed this instead.

    It therefore carries NO `RoomConfiguration`: the room already dispatches,
    and a second dispatch would put two agents in one room, both greeting.
    """
    grants = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=True,
        can_publish_data=True,
        can_subscribe=True,
    )
    token = (
        api.AccessToken(os.getenv("LIVEKIT_API_KEY", "devkey"), _secret())
        .with_identity(identity)
        .with_attributes({"tenant": tenant, "role": "caller"})
        .with_grants(grants)
        .to_jwt()
    )
    return {
        "url": os.getenv("LIVEKIT_URL", "ws://localhost:7880"),
        "room": room,
        "identity": identity,
        "token": token,
    }


def fleet() -> str:
    """The agent_name this deployment dispatches to — never empty (empty = implicit dispatch)."""
    return os.getenv("FLEET", "cc")


def _secret() -> str:
    return os.getenv("LIVEKIT_API_SECRET", "secret")
