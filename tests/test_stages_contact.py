"""The number the clinic reaches a patient on: validated by its tail, changed once agreed."""

import importlib

import pytest

from convo.domain.tools import SideEffect
from convo.tools import confirm
from convo.tools.guard import ToolRefused
from tests.fixtures.clinic import (
    ANA,
    NEW_NUMBER,
    contact_args,
    helpers_module,
    identify,
    messages_module,
    project_module,
    run_context,
    stages,
    tc,  # noqa: F401  (fixtures)
)

pytestmark = pytest.mark.unit


# --- the number the clinic reaches a patient on -----------------------------


async def test_a_new_number_lands_on_every_appointment_of_the_same_patient(tc) -> None:
    """A phone belongs to a person, not to a row: the clinic must not ring the old one next."""
    agenda = tc.adapters["agenda"]
    agenda.book["ap-20260910-0900-derm"] = {**agenda.book[ANA], "when": "2026-09-10T09:00"}

    written = await agenda.execute("update_contact", {"appointment_id": ANA, "phone": NEW_NUMBER})

    assert written == {"appointment_id": ANA, "phone": NEW_NUMBER}
    assert agenda.book[ANA]["phone"] == NEW_NUMBER
    assert agenda.book["ap-20260910-0900-derm"]["phone"] == NEW_NUMBER


async def test_a_number_is_never_written_onto_a_record_the_book_does_not_hold(tc) -> None:
    """The identifier IS the caller's identity here: an unknown one is a stranger, not a row."""
    agenda = tc.adapters["agenda"]

    with pytest.raises(ValueError, match="unknown appointment"):
        await agenda.execute("update_contact", {"appointment_id": "ap-nobody", "phone": NEW_NUMBER})

    assert "ap-nobody" not in agenda.book


async def test_a_number_that_is_not_nine_digits_never_reaches_the_record(tc) -> None:
    agenda = tc.adapters["agenda"]

    with pytest.raises(ValueError, match="not a phone number"):
        await agenda.execute("update_contact", {"appointment_id": ANA, "phone": "689 00"})

    assert agenda.book[ANA]["phone"] == "600123456"


async def test_update_contact_never_reaches_the_record_without_a_confirmation_token(tc) -> None:
    agenda = tc.adapters["agenda"]

    with pytest.raises(ToolRefused, match="no confirmation token"):
        await tc.tools.call("update_contact", contact_args(tc))

    assert agenda.calls == [], "a refused irreversible call must never reach the adapter"
    assert agenda.book[ANA]["phone"] == "600123456"


async def test_a_confirmed_change_writes_the_number_and_leaves_the_cita_alone(tc) -> None:
    agenda, sms = tc.adapters["agenda"], tc.adapters["sms"]
    args = contact_args(tc)
    confirm.mint(tc, "update_contact", args)

    await tc.tools.call("update_contact", args)

    assert [call[0] for call in agenda.calls] == ["update_contact"]
    assert agenda.book[ANA]["phone"] == NEW_NUMBER
    assert agenda.book[ANA]["when"] == "2026-09-03T10:00", "a data change moves no hour"
    assert sms.sent == [], "nothing is sent to a number we have just been told is wrong"


async def test_a_caller_the_book_does_not_hold_is_refused_the_verb_and_never_asked_for_a_number(
    tc,
) -> None:
    """Criterion of the card, at the door the errand is actually entered through.

    `Identify` is where a caller becomes a record, and `start_contact_update`
    looks them up before it hands anything over. Nobody found means no handoff,
    no `tc.customer`, and a sentence that tells the model not to ask for the new
    number — there would be nowhere to put it.
    """
    stage = stages.Identify(tc)
    tc.customer = None

    said = await stage.start_contact_update(run_context(tc), name="Ramón Pérez del Río")

    assert said == identify.NO_RECORD_TO_CHANGE
    assert not isinstance(said, tuple) and not isinstance(said, stages.UpdateContact)
    assert tc.customer is None, "nobody was identified, so nobody is on the context"
    assert stage.errand == identify.APPOINTMENT


async def test_an_unidentified_session_cannot_reach_the_write_even_from_inside_the_stage(
    tc,
) -> None:
    """The second lock. A stage can be rewritten; the record must still refuse a stranger.

    A context whose customer carries no `appointment_id` is what an unidentified
    caller looks like one layer in. The tool answers the model with a sentence,
    the adapter is never called, and Ana's number is where it was.
    """
    tc.customer = {"patient": "Alguien Que Llama", "phone": "600000000"}
    agenda = tc.adapters["agenda"]

    said = await stages.UpdateContact(tc).request_contact_change(run_context(tc), NEW_NUMBER)

    assert said == messages_module.CONTACT_UPDATE_FAILED
    assert agenda.calls == []
    assert agenda.book[ANA]["phone"] == "600123456"


def test_the_number_on_file_crosses_the_handoff_as_three_digits_and_nothing_more(tc) -> None:
    """The safeguard is the value, not the paragraph: the stage cannot say what it never got."""
    previous = tc.prev_agent
    previous.errand = identify.CONTACT

    summary = previous.summary()

    assert "acaba en 456" in summary
    assert "600123456" not in summary
    assert "Ana García Ruiz" in summary


def test_the_same_identification_still_hands_a_rescheduling_the_whole_appointment(tc) -> None:
    """The masking is per errand, not per project: ChooseSlot still needs what it needs."""
    summary = tc.prev_agent.summary()

    assert "600123456" in summary
    assert "jueves 3 de septiembre a las 10:00" in summary


def test_the_confirmation_reads_the_new_number_out_in_groups_a_person_can_check() -> None:
    """Nine digits in a row are read as one cardinal, which nobody can compare to anything."""
    said = helpers_module.contact_confirmation_question(NEW_NUMBER)

    assert said == "Su nuevo teléfono de contacto sería el 689 000 111. ¿Se lo cambio?"


def test_a_number_the_caller_said_is_read_however_they_grouped_it() -> None:
    assert helpers_module.normalise_phone("689 00 01 11") == NEW_NUMBER
    assert helpers_module.normalise_phone("689-000-111") == NEW_NUMBER
    assert helpers_module.normalise_phone("689 000") == "", "eight digits is a misheard number"
    assert helpers_module.masked_phone("600123456") == "acaba en 456"


def test_the_log_line_of_a_change_names_the_record_and_only_the_tail_of_the_number() -> None:
    """The one summary written already masked: `68*******` would tell an auditor nothing."""
    agenda_module = importlib.import_module("tenants.clinica-norte.adapters.agenda")

    line = agenda_module.summarise_contact({"appointment_id": ANA, "phone": NEW_NUMBER})

    assert line == f"appointment {ANA} now reachable on a number ending 111"
    assert NEW_NUMBER not in line


def test_update_contact_is_irreversible_and_declares_no_undo() -> None:
    """An irreversible write with a compensation would be a `write`: nobody keeps the old one."""
    spec = project_module.PROJECT.tools.get("update_contact")

    assert spec.side_effect is SideEffect.IRREVERSIBLE
    assert spec.needs_confirmation() is True
    assert spec.compensation is None
    assert spec.masks("phone")
