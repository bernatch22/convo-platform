"""Session tokens: one caller's ticket into one new room, with the agent dispatched to it.

Tenant isolation lives in this module, not in the SFU: a LiveKit API key can
sign for any room, so the exact-string room grant minted here is the fence.
The JWT also carries `RoomAgentDispatch(agent_name=FLEET, metadata=SessionMeta)`
— the same JSON `core.router.resolve` reads — so who a session is for is
decided once, at the door, and travels with the room.

`mint_observer` is the second ticket this module signs: the same fence, with
the publish rights removed, so a supervisor can listen to a call in progress
without the caller ever learning that somebody joined.

Open source note: `mint_session` is a generic recipe for explicit agent
dispatch on livekit-agents 1.7 — a JWT from plain args, no server round-trip.
"""

import os
import uuid

from livekit import api

from core.contracts import SessionMeta


def public_url() -> str:
    """The LiveKit URL a BROWSER connects to — public and TLS behind Caddy.

    The worker joins over `LIVEKIT_URL` (loopback on the box, `ws://127.0.0.1:7880`);
    a browser cannot use that, so a session token carries `LIVEKIT_PUBLIC_URL`
    (`wss://lk.bernardocastro.dev`) when set, and falls back to `LIVEKIT_URL`
    for the laptop stack where the two are the same.
    """
    return os.getenv("LIVEKIT_PUBLIC_URL") or os.getenv("LIVEKIT_URL", "ws://localhost:7880")


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
    return {"url": public_url(), "room": room, "token": token}


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
        "url": public_url(),
        "room": room,
        "identity": identity,
        "token": token,
    }


def fleet() -> str:
    """The agent_name this deployment dispatches to — never empty (empty = implicit dispatch)."""
    return os.getenv("FLEET", "cc")


def _secret() -> str:
    return os.getenv("LIVEKIT_API_SECRET", "secret")
