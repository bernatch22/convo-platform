"""Session tokens: one caller's ticket into one new room, with the agent dispatched to it.

Decisions: docs/decisions/convo.api.auth.md
"""

import datetime
import os
import uuid
from typing import Literal

from livekit import api

from convo.domain.contracts import SessionMeta
from convo.supervision.supervisor import SUPERVISOR_PREFIX

# What a supervisor asked to be allowed to do. The grants below are the answer.
SupervisorCapability = Literal["listen", "whisper", "takeover"]

# Short-lived on purpose: long enough to walk into a call, too short to keep.
SUPERVISOR_TTL = datetime.timedelta(minutes=15)

# One row per capability — the whole difference between listening and taking the line.
_SUPERVISOR_GRANTS: dict[str, dict[str, bool]] = {
    # Hears the room and reads its transcription; no microphone, no data, not in the list.
    "listen": {
        "can_publish": False,
        "can_publish_data": False,
        "can_subscribe": True,
        "hidden": True,
    },
    # Still silent and still hidden, but may send data — the channel a whisper travels on.
    "whisper": {
        "can_publish": False,
        "can_publish_data": True,
        "can_subscribe": True,
        "hidden": True,
    },
    # The human takes the line: a real microphone, and a participant the caller can see.
    "takeover": {
        "can_publish": True,
        "can_publish_data": True,
        "can_subscribe": True,
        "hidden": False,
    },
}


def public_url() -> str:
    """The LiveKit URL a BROWSER connects to — public and TLS behind Caddy."""
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
    """A listen-only ticket into ONE existing room: subscribe, never publish, never appear."""
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


def mint_caller(room: str, tenant: str, identity: str = "caller") -> dict[str, str]:
    """A speaking ticket into ONE room that ALREADY has its agent dispatched."""
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
        "url": public_url(),
        "room": room,
        "identity": identity,
        "token": token,
    }


def mint_supervisor(
    room: str, capability: SupervisorCapability = "listen", user_id: str = ""
) -> dict[str, str]:
    """Mint one supervisor's short-lived ticket into ONE live room, scoped to one capability."""
    grants = _SUPERVISOR_GRANTS.get(capability)
    if grants is None:
        known = sorted(_SUPERVISOR_GRANTS)
        raise ValueError(f"unknown supervisor capability {capability!r}; known: {known}")
    identity = f"{SUPERVISOR_PREFIX}{user_id or uuid.uuid4().hex[:8]}"
    token = (
        api.AccessToken(os.getenv("LIVEKIT_API_KEY", "devkey"), _secret())
        .with_identity(identity)
        .with_attributes({"role": "supervisor", "cap": capability})
        .with_ttl(SUPERVISOR_TTL)
        .with_grants(api.VideoGrants(room_join=True, room=room, **grants))
        .to_jwt()
    )
    return {
        "url": public_url(),
        "room": room,
        "identity": identity,
        "capability": capability,
        "token": token,
    }


def fleet() -> str:
    """The agent_name this deployment dispatches to — never empty (empty = implicit dispatch)."""
    return os.getenv("FLEET", "cc")


def _secret() -> str:
    return os.getenv("LIVEKIT_API_SECRET", "secret")
