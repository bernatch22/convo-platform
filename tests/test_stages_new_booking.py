"""A caller with no cita at all: the second irreversible door."""

import pytest

from convo.tools import confirm
from convo.tools.guard import ToolRefused
from convo.tools.saga import SagaFailed
from tests.fixtures.clinic import (
    PEDRO,
    REFUSED_13,
    THURSDAY_11,
    helpers_module,
    new_booking,
    new_booking_args,
    unknown,  # noqa: F401  (fixtures)
)

pytestmark = pytest.mark.unit


# --- a caller with no cita at all -------------------------------------------


async def test_a_cita_can_be_created_for_somebody_the_book_never_held(unknown) -> None:
    agenda = unknown.adapters["agenda"]

    written = await agenda.execute(
        "create_appointment", {**PEDRO, "slot_id": THURSDAY_11["id"], "doctor": "Dra. Ruiz"}
    )

    assert written["appointment_id"] == "ap-20260903-1100-trau"
    assert agenda.book[written["appointment_id"]]["patient"] == PEDRO["patient"]
    assert agenda.booked() == [agenda.book[written["appointment_id"]]]


async def test_a_cita_is_never_created_for_a_patient_with_no_name_or_no_number(unknown) -> None:
    """The row IS the record of them, and the SMS has to go somewhere."""
    agenda = unknown.adapters["agenda"]

    with pytest.raises(ValueError, match="name and phone"):
        await agenda.execute("create_appointment", {"slot_id": THURSDAY_11["id"], "phone": "600"})


async def test_create_appointment_never_reaches_the_agenda_without_a_token(unknown) -> None:
    agenda = unknown.adapters["agenda"]

    with pytest.raises(ToolRefused, match="no confirmation token"):
        await unknown.tools.call("create_appointment", new_booking_args(unknown, THURSDAY_11))

    assert agenda.calls == [], "a refused irreversible call must never reach the adapter"


async def test_a_confirmed_new_booking_takes_the_hour_and_writes_to_the_patient(unknown) -> None:
    agenda, sms = unknown.adapters["agenda"], unknown.adapters["sms"]
    args = new_booking_args(unknown, THURSDAY_11)
    confirm.mint(unknown, "create_appointment", args)

    await new_booking._booking(unknown, THURSDAY_11, args).run()

    assert [c[0] for c in agenda.calls] == ["create_appointment"], "no old hour to release"
    assert agenda.booked()[0]["specialty"] == "traumatología"
    assert sms.sent[0]["to"] == PEDRO["phone"]
    assert "jueves 3 de septiembre a las 11:00" in sms.sent[0]["text"]


async def test_a_refused_hour_leaves_a_new_patient_with_nothing_on_the_book(unknown) -> None:
    agenda, sms = unknown.adapters["agenda"], unknown.adapters["sms"]
    args = new_booking_args(unknown, REFUSED_13)
    confirm.mint(unknown, "create_appointment", args)

    with pytest.raises(SagaFailed) as failure:
        await new_booking._booking(unknown, REFUSED_13, args).run()

    assert failure.value.step == "create_appointment"
    assert agenda.booked() == [], "nothing was written, so there is nothing to be told about"
    assert sms.sent == []


async def test_a_failed_sms_takes_the_cita_it_had_just_created_back_off_the_book(unknown) -> None:
    """The compensation needs the id the WRITE produced, not the slot id it was called with.

    A rebooking gets away with the saga's default — its cancel was already keyed
    by appointment — and a creation does not: the argument that undoes it does
    not exist until the row does. Without `undo_args` the cancel is handed a
    `slot_id`, raises `unknown appointment ''`, and the patient is left holding a
    cita nobody ever told them about.
    """
    agenda, sms = unknown.adapters["agenda"], unknown.adapters["sms"]
    # A name the SMS gateway cannot fit in one message: the write goes through, the
    # second step does not. Deterministic, and it needs no monkeypatching.
    unknown.customer = {"patient": "Pedro " + "Ramos " * 90, "phone": PEDRO["phone"]}
    args = new_booking_args(unknown, THURSDAY_11)
    confirm.mint(unknown, "create_appointment", args)

    with pytest.raises(SagaFailed) as failure:
        await new_booking._booking(unknown, THURSDAY_11, args).run()

    assert failure.value.step == "send_sms"
    assert failure.value.compensated == ["create_appointment"]
    assert [c[0] for c in agenda.calls] == ["create_appointment", "cancel_slot"]
    assert agenda.book["ap-20260903-1100-trau"]["status"] == "cancelled"
    assert sms.sent == []


def test_the_new_booking_confirmation_asks_to_reserve_and_never_to_change(unknown) -> None:
    """Nothing is being moved, so «¿lo confirmo?» would name a change that does not exist."""
    said = helpers_module.new_confirmation_question(THURSDAY_11)

    assert said == "jueves 3 de septiembre a las once de la mañana con Dra. Ruiz, ¿se la reservo?"
