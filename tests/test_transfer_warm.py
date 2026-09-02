"""Warm transfer: the briefing is inaudible to the caller, and one log line per attempt."""

import pytest

from convo.supervision.control import NotASupervisor, SupervisorControl
from convo.supervision.supervisor import TRANSFER
from convo.telephony import handover, transfer
from convo.telephony.transfer import COLD, WARM, TransferRefused
from tests.fixtures.transfer import (  # noqa: F401  (fixtures)
    CALLER,
    MOBILE,
    SUP,
    TRUNK,
    FakeRoom,
    FakeSession,
    Person,
    _sip_error,
    control,
    livekit,
    tc,
)

pytestmark = pytest.mark.unit


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
