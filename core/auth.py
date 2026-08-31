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

`mint_supervisor` is that idea with a role on it. One human, one identity
(`sup:<uid>`), three capabilities, and one grant shape per capability — so
what a supervisor may do in a room is decided here, by the signature on a
token, and not by anything the browser sends afterwards. The tokens are
short-lived by design: a supervisor's ticket outliving the call it was minted
for is a standing key to a room.

Open source note: `mint_session` is a generic recipe for explicit agent
dispatch on livekit-agents 1.7 — a JWT from plain args, no server round-trip;
`mint_supervisor` is the same recipe for role-scoped humans.
"""

import datetime
import os
import uuid
from typing import Literal

from livekit import api

from core.contracts import SessionMeta
from core.security.supervisor import SUPERVISOR_PREFIX

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
        "url": public_url(),
        "room": room,
        "identity": identity,
        "token": token,
    }


def mint_supervisor(
    room: str, capability: SupervisorCapability = "listen", user_id: str = ""
) -> dict[str, str]:
    """Mint one supervisor's short-lived ticket into ONE live room, scoped to one capability.

    → `{url, room, identity: "sup:<uid>", capability, token}`

    The identity is the trust anchor: the SFU puts it on every packet and RPC
    the supervisor sends, the agent gates on it with
    `core.security.supervisor.is_supervisor`, and nothing in a payload can
    forge it. A signed `{"role": "supervisor", "cap": …}` attribute rides
    along so a reader that already trusts the identity can also see which
    powers were handed out, without decoding the grants.

    The same human keeps the same identity across capabilities on purpose:
    LiveKit admits one connection per identity, so swapping a `listen` ticket
    for a `takeover` one upgrades the participant already in the room instead
    of adding a second ghost of the same person.
    """
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
