"""Cold transfer: the destination parsed, the carrier's answer read, a failure keeps the caller."""

import pytest

from convo.supervision.supervisor import TRANSFER
from convo.telephony import handover, transfer
from convo.telephony.transfer import COLD, TransferRefused
from tests.fixtures.transfer import (  # noqa: F401  (fixtures)
    CALLER,
    MOBILE,
    ROOM,
    SUP,
    _answer,
    _sip_error,
    control,
    livekit,
    tc,
)

pytestmark = pytest.mark.unit


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
