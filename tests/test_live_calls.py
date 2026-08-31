"""Watching a call in progress: what the SFU says is live, and the ticket to listen in."""

import os

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from api import app, open_store
from core import rooms
from core.state.events import Event
from core.state.store import MemoryStore, SessionRow

pytestmark = pytest.mark.unit

PHONE = "+34910000000"
WEB_ROOM = {
    "room": "tienda-sur-pedidos-ab12cd34",
    "sid": "RM_web",
    "participants": 2,
    "started_at": 300.0,
    "agent": True,
    "identities": ["tienda-sur:u1", "agent-cc"],
    "phone": None,
}
PHONE_ROOM = {
    "room": "call-_+34910000000_xY",
    "sid": "RM_sip",
    "participants": 2,
    "started_at": 400.0,
    "agent": True,
    "identities": ["sip_+34600111222", "agent-cc"],
    "phone": PHONE,
}


@pytest.fixture
def store() -> MemoryStore:
    """One web session and one phone session, both still running."""
    store = MemoryStore()
    store.open_session(SessionRow("AJ_web", "tienda-sur", "pedidos", "chat", started_at=300.0))
    store.append("AJ_web", Event(1, "session.start", 0, {"tenant": "tienda-sur"}))
    store.open_session(
        SessionRow("AJ_call", "clinica-norte", "reagendamiento", "voice", started_at=400.0)
    )
    sip = {"sip.trunkPhoneNumber": PHONE, "sip.callID": "TW-1"}
    store.append("AJ_call", Event(1, "session.start", 0, {"tenant": "clinica-norte", "sip": sip}))
    return store


@pytest.fixture
def client(store: MemoryStore) -> TestClient:
    app.dependency_overrides[open_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def live(monkeypatch, *views) -> None:
    """Answer `/live-calls` with these rooms instead of asking a LiveKit server."""

    async def active_rooms() -> list[dict]:
        return list(views)

    monkeypatch.setattr(rooms, "active_rooms", active_rooms)


def test_a_web_room_is_matched_to_its_session_by_the_project_in_its_name(
    client, monkeypatch
) -> None:
    live(monkeypatch, WEB_ROOM)

    call = client.get("/live-calls").json()[0]

    assert call["room"] == WEB_ROOM["room"] and call["participants"] == 2
    assert (call["session_id"], call["project"]) == ("AJ_web", "pedidos")


def test_a_phone_room_is_matched_by_the_number_the_caller_dialled(client, monkeypatch) -> None:
    live(monkeypatch, PHONE_ROOM)

    call = client.get("/live-calls").json()[0]

    assert call["phone"] == PHONE, "an inbound call never passed through /token"
    assert (call["session_id"], call["tenant"]) == ("AJ_call", "clinica-norte")


def test_a_room_nothing_has_logged_yet_is_still_listed_and_watchable(client, monkeypatch) -> None:
    live(monkeypatch, {**WEB_ROOM, "room": "someone-elses-room", "phone": None})

    call = client.get("/live-calls").json()[0]

    assert call["session_id"] is None and call["room"] == "someone-elses-room"


def test_an_unreachable_sfu_is_a_503_and_never_an_empty_list(client, monkeypatch) -> None:
    async def unreachable() -> list[dict]:
        raise rooms.RoomsUnreachable("livekit: connection refused")

    monkeypatch.setattr(rooms, "active_rooms", unreachable)

    reply = client.get("/live-calls")

    assert reply.status_code == 503 and "connection refused" in reply.json()["detail"]


def test_the_observer_token_may_listen_to_one_room_and_publish_nothing(client) -> None:
    reply = client.post("/observe", json={"room": PHONE_ROOM["room"]}).json()

    grants = _decoded(reply["token"])["video"]
    assert grants["room"] == PHONE_ROOM["room"] and grants["roomJoin"] is True
    assert not grants.get("canPublish"), "an observer has no microphone, whatever the browser does"
    assert not grants.get("canPublishData")
    assert grants["canSubscribe"] is True and grants["hidden"] is True
    assert reply["identity"].startswith("observer:")


def test_the_observer_token_carries_no_agent_dispatch(client) -> None:
    claims = _decoded(client.post("/observe", json={"room": "any"}).json()["token"])

    assert "roomConfig" not in claims, "an observer joins a call; it never starts one"


def test_observe_needs_a_room_and_refuses_anything_else(client) -> None:
    assert client.post("/observe", json={}).status_code == 422
    assert client.post("/observe", json={"room": "r", "identity": "spy"}).status_code == 422


def _decoded(token: str) -> dict:
    """Read a minted token with the secret this deploy actually signed it with."""
    secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    return pyjwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
