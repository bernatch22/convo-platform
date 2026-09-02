"""Fixtures and fakes shared by the transfer tests."""

import asyncio
from typing import Any

import pytest
from livekit.api import SipCallError
from livekit.protocol.sip import SIPTransferStatus

from convo.supervision.control import SupervisorControl
from convo.telephony import handover
from convo.testing import fake_context

SUP = "sup:berna"
CALLER = "sip_+34600111222"
AGENT = "agent-cc"
ROOM = "call-_+34600111222_abc"
MOBILE = "+34600999888"
TRUNK = "ST_outbound"


# ── the fakes: exactly the surface a transfer touches ─────────────────────────


class Track:
    def __init__(self, sid: str) -> None:
        self.sid = sid


class Person:
    def __init__(self, identity: str, kind: int = 3, tracks: tuple[str, ...] = ()) -> None:
        self.identity = identity
        self.kind = kind
        self.tracks = [Track(sid) for sid in tracks]


class FakeRoom:
    """An `rtc.Room` reduced to the three things a handover reads off it."""

    def __init__(self, people: dict[str, Person] | None = None) -> None:
        self.name = ROOM
        self.local_participant = Person(AGENT, kind=4)
        self.remote_participants = people if people is not None else {CALLER: Person(CALLER)}


class FakeSip:
    def __init__(self) -> None:
        self.transfers: list[Any] = []
        self.dials: list[Any] = []
        self.transfer_answer: Any = None
        self.transfer_raises: Exception | None = None
        self.dial_raises: Exception | None = None

    async def transfer_sip_participant(self, request):
        self.transfers.append(request)
        if self.transfer_raises is not None:
            raise self.transfer_raises
        return self.transfer_answer if self.transfer_answer is not None else _answer("ok")

    async def create_sip_participant(self, request):
        self.dials.append(request)
        if self.dial_raises is not None:
            raise self.dial_raises
        self.room.arrive(request.participant_identity, "TR_human")
        return object()


class FakeRoomService:
    def __init__(self, people: list[Person]) -> None:
        self.people = people
        self.subscriptions: list[tuple[str, tuple[str, ...], bool]] = []
        self.removed: list[str] = []

    async def list_participants(self, request):
        return type("Answer", (), {"participants": list(self.people)})()

    async def update_subscriptions(self, request):
        self.subscriptions.append((request.identity, tuple(request.track_sids), request.subscribe))

    async def remove_participant(self, request):
        self.removed.append(request.identity)

    def arrive(self, identity: str, sid: str) -> None:
        self.people.append(Person(identity, kind=3, tracks=(sid,)))


class FakeAPI:
    """The LiveKit API with only what a transfer calls, and a record of every call."""

    def __init__(self) -> None:
        self.room = FakeRoomService(
            [Person(CALLER, 3, ("TR_caller",)), Person(AGENT, 4, ("TR_agent",))]
        )
        self.sip = FakeSip()
        self.sip.room = self.room
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeAgent:
    def __init__(self) -> None:
        from livekit.agents.llm import ChatContext

        self.chat_ctx = ChatContext()
        self.updates: list[Any] = []

    async def update_chat_ctx(self, chat_ctx) -> None:
        self.updates.append(chat_ctx)
        self.chat_ctx = chat_ctx


class FakeSession:
    """A session that remembers what it was asked to say and to generate."""

    def __init__(self) -> None:
        self.current_agent = FakeAgent()
        self.agent_state = "listening"
        self.current_speech = None
        self.said: list[str] = []
        self.replies: list[dict[str, Any]] = []
        self.input = type("Input", (), {"set_audio_enabled": lambda self, on: None})()
        self.options = type("Options", (), {"interruption": {}})()

    def say(self, line: str, **kwargs: Any) -> None:
        self.said.append(line)

    def generate_reply(self, **kwargs: Any) -> None:
        self.replies.append(kwargs)

    def interrupt(self, *, force: bool = False):
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        done.set_result(None)
        return done


def _answer(kind: str, code: int = 0):
    status = {
        "ok": SIPTransferStatus.STS_TRANSFER_SUCCESSFUL,
        "ongoing": SIPTransferStatus.STS_TRANSFER_ONGOING,
        "failed": SIPTransferStatus.STS_TRANSFER_FAILED,
    }[kind]
    return type("Answer", (), {"status": status, "sip_status": type("S", (), {"code": code})()})()


def _sip_error(code: int, reason: str = "") -> SipCallError:
    return SipCallError(
        "internal",
        reason or f"sip {code}",
        status=500,
        metadata={"sip_status_code": str(code), "sip_status": reason},
    )


@pytest.fixture
def tc():
    return fake_context("clinica-norte", "reagendamiento")


@pytest.fixture
def livekit(monkeypatch) -> FakeAPI:
    api_client = FakeAPI()
    monkeypatch.setattr(handover, "client", lambda: api_client)
    return api_client


@pytest.fixture
def control(tc, livekit) -> SupervisorControl:
    control = SupervisorControl(tc, FakeSession(), FakeRoom())
    tc.supervisor = control
    return control
