"""Moving a live call to a human: cold REFER, warm dial-in, and the failures that keep the caller.

Five claims are pinned here, one per section.

1. A destination is parsed before anything is dialled. A transfer that was
   never attempted has to be told to the DESK; one that was attempted and
   failed has to be told to the CALLER, and the two are different returns.
2. Cold transfer reads the carrier's answer, including the answer that arrives
   as a 200 with `STS_TRANSFER_FAILED` inside it — the one shape that looks
   like success and is not.
3. A failed transfer leaves the caller where they were, and tells them so: the
   note is in the agent's own context BEFORE the turn is asked for, because
   `generate_reply` only appends instructions (agents#3820).
4. The warm briefing is inaudible to the caller. The agent's track is cut
   BEFORE the colleague is dialled and the colleague's the instant they
   answer; the bridge puts both back; a leg that never answers puts them back
   too, so nobody is left deaf on a call that did not move.
5. Every transfer is one `supervisor.transfer` line in the CALLER's log,
   carrying the mode and the outcome, and only a signed `sup:` identity can
   cause one.

The LiveKit API is a fake with the five methods a transfer actually calls,
which is itself the assertion that this reaches no further into the SFU
than that.
"""

import asyncio
from typing import Any

import pytest
from livekit.api import SipCallError
from livekit.protocol.sip import SIPTransferStatus

from core.security.control import NotASupervisor, SupervisorControl
from core.security.supervisor import TRANSFER
from core.telephony import handover, transfer
from core.telephony.transfer import COLD, WARM, TransferRefused
from core.testing import fake_context

pytestmark = pytest.mark.unit

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


# ── 1. a destination is parsed before anything is dialled ────────────────────


def test_a_phone_number_becomes_a_tel_uri_and_a_sip_uri_is_left_alone() -> None:
    assert transfer.dial_uri(" +34600111222 ") == "tel:+34600111222"
    assert (
        transfer.dial_uri("sip:1234@my-trunk.pstn.twilio.com")
        == "sip:1234@my-trunk.pstn.twilio.com"
    )


def test_a_destination_that_is_not_a_number_is_refused_before_the_call_moves() -> None:
    for bad in ("", "   ", "600111222", "+34 600 111 222", "recepción"):
        with pytest.raises(TransferRefused):
            transfer.dial_uri(bad)


def test_the_deployments_own_number_stands_in_when_the_desk_names_none(monkeypatch) -> None:
    monkeypatch.setenv(transfer.TARGET_ENV, MOBILE)

    assert transfer.destination("") == MOBILE
    assert transfer.destination("+34611000000") == "+34611000000"


def test_a_warm_leg_dials_numbers_only_because_the_trunk_takes_a_number() -> None:
    with pytest.raises(TransferRefused, match="E.164"):
        transfer.phone_number("sip:1234@my-trunk.pstn.twilio.com")


# ── 2. cold transfer reads the carrier's answer ──────────────────────────────


async def test_a_cold_transfer_refers_the_callers_own_leg_to_the_number(control, livekit) -> None:
    answered = await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": COLD})

    (request,) = livekit.sip.transfers
    assert request.participant_identity == CALLER
    assert request.room_name == ROOM
    assert request.transfer_to == f"tel:{MOBILE}"
    assert request.play_dialtone is True
    assert answered["outcome"] == transfer.TRANSFERRED
    assert answered["ok"] is True


async def test_a_200_carrying_a_failed_status_is_not_read_as_a_transfer(control, livekit) -> None:
    """The one shape that looks like success: no exception, and the call never moved."""
    livekit.sip.transfer_answer = _answer("failed", code=486)

    answered = await control.apply(TRANSFER, SUP, {"to": MOBILE})

    assert answered["ok"] is False
    assert answered["outcome"] == transfer.BUSY


async def test_a_trunk_that_refuses_the_refer_is_named_as_the_suspect(control, livekit) -> None:
    livekit.sip.transfer_raises = _sip_error(603, "Decline")

    answered = await control.apply(TRANSFER, SUP, {"to": MOBILE})

    assert answered["outcome"] == transfer.REJECTED
    assert answered["sip_status"] == 603
    assert "enable-all" in answered["detail"]


async def test_a_phone_that_rings_out_is_a_no_answer_and_not_a_rejection(control, livekit) -> None:
    livekit.sip.transfer_raises = _sip_error(480, "Temporarily Unavailable")

    answered = await control.apply(TRANSFER, SUP, {"to": MOBILE})

    assert answered["outcome"] == transfer.NO_ANSWER
    assert answered["ok"] is False


async def test_an_sfu_that_cannot_be_asked_is_an_outcome_and_not_a_crash(control, livekit) -> None:
    livekit.sip.transfer_raises = RuntimeError("connection refused")

    answered = await control.apply(TRANSFER, SUP, {"to": MOBILE})

    assert answered["outcome"] == transfer.UNREACHABLE
    assert answered["ok"] is False


# ── 3. a failed transfer keeps the caller, and tells them ────────────────────


async def test_the_caller_is_held_before_the_refer_is_sent(control, livekit) -> None:
    await control.apply(TRANSFER, SUP, {"to": MOBILE})

    assert control.session.said == [handover.HOLD_COLD]


async def test_a_failed_transfer_puts_the_reason_in_the_agents_context_then_asks_for_a_turn(
    control, livekit
) -> None:
    livekit.sip.transfer_raises = _sip_error(486, "Busy Here")

    await control.apply(TRANSFER, SUP, {"to": MOBILE})

    (swapped,) = control.session.current_agent.updates
    assert transfer.BUSY in swapped.items[-1].text_content
    assert control.session.replies == [{"instructions": handover.FAILED_INSTRUCTIONS}]


async def test_a_transfer_that_worked_says_nothing_more_to_a_caller_who_has_gone(
    control, livekit
) -> None:
    await control.apply(TRANSFER, SUP, {"to": MOBILE})

    assert control.session.replies == []
    assert control.session.current_agent.updates == []


# ── 4. the warm briefing is inaudible to the caller ──────────────────────────


async def test_a_warm_transfer_needs_an_outbound_trunk_and_says_which_one(control, monkeypatch, tc):
    monkeypatch.delenv(transfer.TRUNK_ENV, raising=False)

    with pytest.raises(TransferRefused, match=transfer.TRUNK_ENV):
        await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": WARM})

    assert [event.kind for event in tc.log.events() if event.kind == TRANSFER] == []


async def test_the_caller_stops_hearing_the_agent_before_the_colleague_is_dialled(
    control, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)

    await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": WARM})

    cut_first = livekit.room.subscriptions[0]
    assert cut_first == (CALLER, ("TR_agent",), False)
    assert livekit.sip.dials, "the colleague was never dialled"


async def test_the_colleague_is_cut_out_of_the_callers_ears_the_moment_they_answer(
    control, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)

    await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": WARM})

    cuts = [call for call in livekit.room.subscriptions if call[2] is False]
    assert ("TR_human",) in [call[1] for call in cuts]


async def test_the_briefing_is_spoken_into_the_cut_line_and_then_the_three_are_bridged(
    control, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)

    answered = await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": WARM})

    assert {"instructions": handover.BRIEF_INSTRUCTIONS} in control.session.replies
    bridged = livekit.room.subscriptions[-1]
    assert bridged[0] == CALLER and bridged[2] is True
    assert set(bridged[1]) == {"TR_agent", "TR_human"}
    assert answered["outcome"] == transfer.BRIDGED


async def test_a_bridged_call_leaves_the_agent_muted_so_it_is_not_a_third_voice(
    control, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)

    await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": WARM})

    assert control.muted is True
    assert control.held_by == SUP


async def test_a_colleague_who_does_not_answer_gives_the_caller_their_audio_back(
    control, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)
    livekit.sip.dial_raises = _sip_error(480, "Temporarily Unavailable")

    answered = await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": WARM})

    assert answered["outcome"] == transfer.NO_ANSWER
    assert livekit.room.subscriptions[-1] == (CALLER, ("TR_agent",), True)
    assert control.muted is False


# ── 5. one line in the caller's log, and only a supervisor causes one ────────


async def test_every_transfer_is_one_log_line_carrying_its_mode_and_its_outcome(
    control, livekit, tc
) -> None:
    livekit.sip.transfer_raises = _sip_error(486, "Busy Here")

    await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": COLD})

    (event,) = [event for event in tc.log.events() if event.kind == TRANSFER]
    assert event.payload["mode"] == COLD
    assert event.payload["outcome"] == transfer.BUSY
    assert event.payload["identity"] == SUP
    assert event.payload["ok"] is False


async def test_a_transfer_from_any_other_identity_moves_no_call(control, livekit, tc) -> None:
    for identity in (CALLER, "observer:ab12", "", "supervisor:berna"):
        with pytest.raises(NotASupervisor):
            await control.apply(TRANSFER, identity, {"to": MOBILE})

    assert livekit.sip.transfers == []
    assert [event.kind for event in tc.log.events() if event.kind == TRANSFER] == []


async def test_a_session_with_no_room_is_refused_the_verb_rather_than_guessing(tc) -> None:
    """The console has no room, no caller and no SIP leg: there is nothing to transfer."""
    control = SupervisorControl(tc, FakeSession())

    with pytest.raises(TransferRefused, match="no room"):
        await control.apply(TRANSFER, SUP, {"to": MOBILE})


async def test_a_room_with_nobody_but_the_agent_and_a_supervisor_has_no_caller(tc, livekit) -> None:
    room = FakeRoom({SUP: Person(SUP, kind=1)})
    control = SupervisorControl(tc, FakeSession(), room)

    with pytest.raises(TransferRefused, match="no caller"):
        await control.apply(TRANSFER, SUP, {"to": MOBILE})


async def test_an_unknown_transfer_mode_is_refused_by_name(control, livekit) -> None:
    with pytest.raises(TransferRefused, match="tepid"):
        await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": "tepid"})


async def test_a_refusal_before_the_dial_promises_the_caller_nothing_and_cuts_nothing(
    control, livekit, monkeypatch
) -> None:
    """The order matters: a warm leg with no trunk must not leave a deaf caller on hold."""
    monkeypatch.delenv(transfer.TRUNK_ENV, raising=False)

    with pytest.raises(TransferRefused):
        await control.apply(TRANSFER, SUP, {"to": MOBILE, "mode": WARM})

    assert control.session.said == []
    assert livekit.room.subscriptions == []


async def test_a_cold_transfer_to_a_number_that_is_not_one_says_nothing_to_the_caller(
    control, livekit
) -> None:
    with pytest.raises(TransferRefused):
        await control.apply(TRANSFER, SUP, {"to": "recepción"})

    assert control.session.said == []
    assert livekit.sip.transfers == []
