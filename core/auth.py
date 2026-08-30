"""Session tokens: one caller's ticket into one new room, with the agent dispatched to it.

Tenant isolation lives in this module, not in the SFU: a LiveKit API key can
sign for any room, so the exact-string room grant minted here is the fence.
The JWT also carries `RoomAgentDispatch(agent_name=FLEET, metadata=SessionMeta)`
— the same JSON `core.router.resolve` reads — so who a session is for is
decided once, at the door, and travels with the room.

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


def fleet() -> str:
    """The agent_name this deployment dispatches to — never empty (empty = implicit dispatch)."""
    return os.getenv("FLEET", "cc")


def _secret() -> str:
    return os.getenv("LIVEKIT_API_SECRET", "secret")
