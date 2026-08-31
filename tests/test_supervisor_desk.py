"""The desk: a supervisor's arrival is what the SFU says it is, and the agent alone is told.

Everything here turns on two refusals. The capability is read off the
participant's signed attributes at the server, never off the request body — a
browser asking to be recorded as `takeover` is asking a field nobody reads.
And the announcement is addressed to the agent by identity, because a
broadcast would deliver "a supervisor joined" into the caller's own browser,
which is the single thing this feature exists not to do.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import app
from core import rooms
from core.security import desk

pytestmark = pytest.mark.unit

ROOM = "call-_+34910000000_xY"


@dataclass
class Permission:
    hidden: bool = False


@dataclass
class Person:
    """A participant as `list_participants` returns one."""

    identity: str
    kind: int = 0
    attributes: dict[str, str] = field(default_factory=dict)
    permission: Permission = field(default_factory=Permission)


@dataclass
class Sent:
    """The one SendDataRequest the desk made, kept so a test can read its destination."""

    request: Any = None


class FakeRoomService:
    def __init__(self, people: list[Person], sent: Sent) -> None:
        self.people = people
        self.sent = sent

    async def list_participants(self, request) -> Any:
        return type("Reply", (), {"participants": self.people})()

    async def send_data(self, request) -> None:
        self.sent.request = request


class FakeClient:
    def __init__(self, people: list[Person], sent: Sent) -> None:
        self.room = FakeRoomService(people, sent)

    async def aclose(self) -> None:
        return None


@pytest.fixture
def sent() -> Sent:
    return Sent()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def in_room(monkeypatch, sent: Sent, *people: Person) -> None:
    """Answer the SFU with exactly these participants instead of asking a LiveKit server."""
    monkeypatch.setattr(rooms, "client", lambda: FakeClient(list(people), sent))


def agent(identity: str = "agent-cc") -> Person:
    return Person(identity=identity, kind=rooms.AGENT_KIND)


def supervisor(capability: str = "listen", hidden: bool = True) -> Person:
    attributes = {"role": "supervisor", "cap": capability}
    return Person("sup:berna", attributes=attributes, permission=Permission(hidden=hidden))


async def test_the_capability_comes_from_the_signed_token_at_the_sfu(monkeypatch, sent) -> None:
    in_room(monkeypatch, sent, agent(), supervisor("whisper"), Person("clinica-norte:u1"))

    seen = await desk.entered(ROOM, "sup:berna")

    assert seen == {
        "identity": "sup:berna",
        "capability": "whisper",
        "hidden": True,
        "announced": True,
    }


async def test_the_arrival_is_announced_to_the_agent_and_to_nobody_else(monkeypatch, sent) -> None:
    in_room(monkeypatch, sent, agent(), supervisor(), Person("clinica-norte:u1"))

    await desk.entered(ROOM, "sup:berna")

    assert sent.request.destination_identities == ["agent-cc"], "a broadcast reaches the caller"
    assert sent.request.topic == "supervisor" and sent.request.room == ROOM
    assert b'"verb": "join"' in sent.request.data


async def test_a_room_with_no_agent_is_announced_to_nobody(monkeypatch, sent) -> None:
    in_room(monkeypatch, sent, supervisor(), Person("clinica-norte:u1"))

    seen = await desk.entered(ROOM, "sup:berna")

    assert seen["announced"] is False
    assert sent.request is None, "there is no log being written in that room either"


async def test_a_ticket_that_was_never_used_is_not_an_arrival(monkeypatch, sent) -> None:
    in_room(monkeypatch, sent, agent(), Person("clinica-norte:u1"))

    with pytest.raises(desk.NotInRoom):
        await desk.entered(ROOM, "sup:berna")
    assert sent.request is None


async def test_only_a_sup_identity_can_be_recorded_as_a_supervisor(monkeypatch, sent) -> None:
    in_room(monkeypatch, sent, agent(), Person("clinica-norte:u1"))

    with pytest.raises(desk.NotInRoom):
        await desk.entered(ROOM, "clinica-norte:u1")


async def test_a_supervisor_the_caller_can_see_is_reported_as_such(monkeypatch, sent) -> None:
    """`hidden` is the server's answer, so the desk can show it rather than assert it."""
    in_room(monkeypatch, sent, agent(), supervisor("takeover", hidden=False))

    seen = await desk.entered(ROOM, "sup:berna")

    assert seen["hidden"] is False and seen["capability"] == "takeover"


def test_the_endpoint_returns_the_presence_and_refuses_an_extra_field(
    client, monkeypatch, sent
) -> None:
    in_room(monkeypatch, sent, agent(), supervisor())

    body = {"room": ROOM, "identity": "sup:berna"}
    extra = {**body, "capability": "takeover"}

    assert client.post("/supervise/entered", json=body).json()["hidden"] is True
    assert client.post("/supervise/entered", json=extra).status_code == 422
    assert client.post("/supervise/entered", json={"room": ROOM}).status_code == 422


def test_an_identity_that_is_not_in_the_room_is_a_404(client, monkeypatch, sent) -> None:
    in_room(monkeypatch, sent, agent())

    reply = client.post("/supervise/entered", json={"room": ROOM, "identity": "sup:ghost"})

    assert reply.status_code == 404 and "sup:ghost" in reply.json()["detail"]


def test_an_sfu_that_cannot_be_asked_is_a_503_and_not_an_empty_room(client, monkeypatch) -> None:
    def broken() -> Any:
        raise rooms.RoomsUnreachable("livekit is not configured")

    monkeypatch.setattr(rooms, "client", broken)

    reply = client.post("/supervise/entered", json={"room": ROOM, "identity": "sup:berna"})

    assert reply.status_code == 503
