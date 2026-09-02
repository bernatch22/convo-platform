"""The clinic's systems, the guard and the saga: what a booking may and may not do."""

import pytest

from convo.domain.tools import SideEffect
from convo.tools import confirm
from convo.tools.guard import ToolRefused
from convo.tools.saga import SagaFailed
from tests.fixtures.clinic import (
    ANA,
    REFUSED_13,
    THURSDAY_11,
    booking_args,
    choose_slot,
    patients,
    project_module,
    tc,  # noqa: F401  (fixtures)
)

pytestmark = pytest.mark.unit


# --- the clinic's systems ---------------------------------------------------


def test_a_patient_is_found_by_phone_or_by_the_name_they_actually_say() -> None:
    book = patients.seeded()

    assert patients.lookup(book, None, "600 123 456")["patient"] == "Ana García Ruiz"
    assert patients.lookup(book, "Ana García", None)["appointment_id"] == ANA
    assert patients.lookup(book, "Pedro Ramos", "699000000") is None


async def test_the_booking_system_always_refuses_a_slot_at_thirteen_hundred(tc) -> None:
    """The demo's deterministic failure, so the compensated path can be shown on demand."""
    agenda = tc.adapters["agenda"]

    with pytest.raises(ValueError, match="refused"):
        await agenda.execute("book_slot", {"slot_id": REFUSED_13["id"], "patient": "Ana"})


async def test_a_cancel_is_undone_by_the_rebook_the_spec_names_as_its_compensation(tc) -> None:
    agenda = tc.adapters["agenda"]

    await agenda.execute("cancel_slot", {"appointment_id": ANA})
    assert agenda.book[ANA]["status"] == "cancelled"

    await agenda.execute("rebook_slot", {"appointment_id": ANA})
    assert agenda.book[ANA]["status"] == "booked"


# --- the guard and the saga -------------------------------------------------


async def test_book_slot_never_reaches_the_agenda_without_a_confirmation_token(tc) -> None:
    agenda = tc.adapters["agenda"]

    with pytest.raises(ToolRefused, match="no confirmation token"):
        await tc.tools.call("book_slot", booking_args(tc, THURSDAY_11))

    assert agenda.calls == [], "a refused irreversible call must never reach the adapter"


async def test_a_confirmed_rebooking_frees_the_old_hour_takes_the_new_one_and_writes(tc) -> None:
    agenda, sms = tc.adapters["agenda"], tc.adapters["sms"]
    args = booking_args(tc, THURSDAY_11)
    confirm.mint(tc, "book_slot", args)

    await choose_slot._rebooking(tc, THURSDAY_11, args).run()

    assert [c[0] for c in agenda.calls] == ["cancel_slot", "book_slot"]
    assert agenda.book[ANA]["status"] == "cancelled"
    assert sms.sent[0]["to"] == "600123456"
    assert "jueves 3 de septiembre a las 11:00" in sms.sent[0]["text"]


async def test_a_refused_hour_puts_the_old_appointment_back_and_sends_nothing(tc) -> None:
    agenda, sms = tc.adapters["agenda"], tc.adapters["sms"]
    args = booking_args(tc, REFUSED_13)
    confirm.mint(tc, "book_slot", args)

    with pytest.raises(SagaFailed) as failure:
        await choose_slot._rebooking(tc, REFUSED_13, args).run()

    assert failure.value.step == "book_slot"
    assert failure.value.compensated == ["cancel_slot"]
    assert [c[0] for c in agenda.calls] == ["cancel_slot", "book_slot", "rebook_slot"]
    assert agenda.book[ANA]["status"] == "booked", "the patient still has the cita she had"
    assert sms.sent == [], "nobody is told about a change that did not happen"


async def test_a_refused_booking_does_not_spend_the_caller_s_yes(tc) -> None:
    """The token is consumed after a successful call, so retrying needs no second yes."""
    args = booking_args(tc, REFUSED_13)
    token = confirm.mint(tc, "book_slot", args)

    with pytest.raises(SagaFailed):
        await choose_slot._rebooking(tc, REFUSED_13, args).run()

    assert token.used is False


def test_every_tool_the_project_can_call_declares_what_it_does_to_the_world() -> None:
    catalog = project_module.PROJECT.tools

    assert catalog.names() == [
        "book_slot",
        "cancel_appointment",
        "cancel_slot",
        "confirm_attendance",
        "create_appointment",
        "find_availability",
        "find_patient",
        "rebook_slot",
        "send_sms",
        "transfer_to_human",
        "update_contact",
    ]
    assert catalog.get("book_slot").side_effect is SideEffect.IRREVERSIBLE
    assert catalog.get("book_slot").needs_confirmation() is True
    assert catalog.get("create_appointment").side_effect is SideEffect.IRREVERSIBLE
    assert catalog.get("create_appointment").needs_confirmation() is True
    assert catalog.get("create_appointment").compensation == "cancel_slot"
    assert catalog.get("cancel_slot").compensation == "rebook_slot"
    assert catalog.get("find_availability").needs_confirmation() is False
