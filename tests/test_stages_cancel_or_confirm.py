"""The two verbs that are not a move: cancel the cita, or confirm attendance."""

import importlib

import pytest

from convo.domain.tools import SideEffect
from convo.testing import fake_context, run_conversation
from convo.tools import confirm
from convo.tools.guard import ToolRefused
from tests.conftest import needs_llm
from tests.fixtures.clinic import (  # noqa: F401  (fixtures)
    ANA,
    _arguments,
    helpers_module,
    identify,
    messages_module,
    project_module,
    run_context,
    settling,
    stages,
    tc,
)

pytestmark = pytest.mark.unit


# --- the two verbs that are not a move --------------------------------------


async def test_a_cancelled_hour_goes_back_on_offer_to_the_next_caller(tc) -> None:
    """The whole reason a cancellation is worth taking: the clinic does not lose the half hour."""
    agenda = tc.adapters["agenda"]
    before = await agenda.execute(
        "find_availability", {"date": "2026-09-03", "specialty": "traumatología"}
    )

    await agenda.execute("cancel_appointment", {"appointment_id": ANA})
    after = await agenda.execute(
        "find_availability", {"date": "2026-09-03", "specialty": "traumatología"}
    )

    assert "sl-20260903-1000-trau" not in [slot["id"] for slot in before]
    freed = next(slot for slot in after if slot["id"] == "sl-20260903-1000-trau")
    assert freed == {
        "id": "sl-20260903-1000-trau",
        "when": "2026-09-03T10:00",
        "doctor": "Dra. Irene Campos",
    }
    assert [slot["when"] for slot in after] == sorted(slot["when"] for slot in after)


async def test_an_hour_given_back_is_offered_once_and_not_after_somebody_takes_it(tc) -> None:
    agenda = tc.adapters["agenda"]
    await agenda.execute("cancel_appointment", {"appointment_id": ANA})

    await agenda.execute(
        "book_slot",
        {"slot_id": "sl-20260903-1000-trau", "patient": "Otro Paciente", "phone": "600000111"},
    )
    after = await agenda.execute(
        "find_availability", {"date": "2026-09-03", "specialty": "traumatología"}
    )

    assert "sl-20260903-1000-trau" not in [slot["id"] for slot in after]


async def test_a_cancelled_hour_is_never_offered_on_another_day_or_specialty(tc) -> None:
    """A traumatología hour is a traumatología hour: the id carries the day and the specialty."""
    agenda = tc.adapters["agenda"]
    await agenda.execute("cancel_appointment", {"appointment_id": ANA})

    elsewhere = await agenda.execute(
        "find_availability", {"date": "2026-09-04", "specialty": "traumatología"}
    )
    general = await agenda.execute("find_availability", {"date": "2026-09-03"})

    assert "sl-20260903-1000-trau" not in [slot["id"] for slot in elsewhere + general]


async def test_a_cancel_slot_inside_a_saga_does_not_put_the_hour_back_on_offer(tc) -> None:
    """The difference between the two cancels, as behaviour and not as a docstring."""
    agenda = tc.adapters["agenda"]

    await agenda.execute("cancel_slot", {"appointment_id": ANA})
    after = await agenda.execute(
        "find_availability", {"date": "2026-09-03", "specialty": "traumatología"}
    )

    assert agenda.freed == {}
    assert "sl-20260903-1000-trau" not in [slot["id"] for slot in after]


async def test_cancel_appointment_never_reaches_the_book_without_a_confirmation_token(tc) -> None:
    agenda = tc.adapters["agenda"]

    with pytest.raises(ToolRefused, match="no confirmation token"):
        await tc.tools.call("cancel_appointment", {"appointment_id": ANA})

    assert agenda.calls == [], "a refused irreversible call must never reach the adapter"
    assert agenda.book[ANA].get("status") is None


async def test_a_confirmed_cancellation_drops_the_cita_and_sends_nobody_an_sms(tc) -> None:
    agenda, sms = tc.adapters["agenda"], tc.adapters["sms"]
    args = {"appointment_id": ANA}
    confirm.mint(tc, "cancel_appointment", args)

    await tc.tools.call("cancel_appointment", args)

    assert [call[0] for call in agenda.calls] == ["cancel_appointment"]
    assert agenda.book[ANA]["status"] == "cancelled"
    assert sms.sent == [], "nothing is promised to a patient who has just dropped their cita"


async def test_confirming_attendance_needs_no_token_and_moves_no_hour(tc) -> None:
    """The one write of this project a caller does not have to agree to twice."""
    agenda = tc.adapters["agenda"]

    written = await tc.tools.call("confirm_attendance", {"appointment_id": ANA})

    assert written == {"appointment_id": ANA, "status": "confirmed"}
    assert agenda.book[ANA]["when"] == "2026-09-03T10:00"
    assert agenda.book[ANA]["doctor"] == "Dra. Irene Campos"


async def test_a_cita_the_book_does_not_hold_is_never_cancelled_or_confirmed(tc) -> None:
    agenda = tc.adapters["agenda"]

    for capability in ("cancel_appointment", "confirm_attendance"):
        with pytest.raises(ValueError, match="unknown appointment"):
            await agenda.execute(capability, {"appointment_id": "ap-nobody"})

    assert "ap-nobody" not in agenda.book


async def test_a_caller_the_book_does_not_hold_is_refused_both_verbs_at_the_door(tc) -> None:
    """Criterion of the card: no cita means nothing to cancel and nothing to confirm."""
    stage = stages.Identify(tc)
    tc.customer = None

    dropped = await stage.start_cancellation(run_context(tc), name="Ramón Pérez del Río")
    kept = await stage.start_attendance_confirmation(run_context(tc), name="Ramón Pérez del Río")

    assert dropped == identify.NO_CITA_TO_CANCEL
    assert kept == identify.NO_CITA_TO_CONFIRM
    assert tc.customer is None, "nobody was identified, so nobody is on the context"
    assert stage.errand == identify.APPOINTMENT


async def test_the_stage_looks_the_cita_up_instead_of_reciting_the_note_it_was_handed(
    settling, tc
) -> None:
    """Every hour this stage says out loud comes back as a tool output, which is evidence."""
    said = await settling.find_my_appointment(run_context(tc))

    assert [call[0] for call in tc.adapters["agenda"].calls] == ["find_patient"]
    assert "jueves 3 de septiembre a las 10:00" in said
    assert "Dra. Irene Campos" in said


async def test_the_lookup_can_only_ever_find_the_caller_on_the_line(settling, tc) -> None:
    """The leak defence is the absence of an argument, not a paragraph in a prompt.

    `find_my_appointment` takes no name, so a caller asking about their husband's
    cita is refused by a stage with no way to ask rather than by a model that
    decided not to.
    """
    assert list(_arguments(settling.find_my_appointment)) == [], (
        "a lookup with a name argument is a lookup that can be pointed at somebody else"
    )
    tc.customer = None

    said = await settling.find_my_appointment(run_context(tc))

    assert said == messages_module.NO_CITA_ON_THE_BOOK
    assert tc.adapters["agenda"].calls == []


async def test_neither_verb_touches_the_book_when_nobody_was_identified(settling, tc) -> None:
    tc.customer = None

    dropped = await settling.request_cancellation(run_context(tc))
    kept = await settling.confirm_attendance(run_context(tc))

    assert dropped == kept == messages_module.NO_CITA_ON_THE_BOOK
    assert tc.adapters["agenda"].calls == []
    assert tc.adapters["agenda"].book[ANA].get("status") is None


def test_the_cancellation_question_is_rendered_by_the_platform_and_names_the_cita() -> None:
    """What the caller agrees to and what the book loses have to be the same thing."""
    said = helpers_module.cancellation_question(
        {"when": "2026-09-03T10:00", "doctor": "Dra. Irene Campos"}
    )

    assert (
        said
        == "jueves 3 de septiembre a las diez de la mañana con Dra. Irene Campos, ¿se la anulo?"
    )


def test_the_cita_is_read_back_with_the_clock_s_hour_and_spoken_with_the_person_s() -> None:
    """`_offer`'s rule, applied to the cita: the shared paragraph turns 10:00 into words."""
    line = helpers_module.appointment_line(
        {
            "when": "2026-09-03T10:00",
            "doctor": "Dra. Irene Campos",
            "specialty": "traumatología",
        }
    )

    assert "jueves 3 de septiembre a las 10:00" in line
    assert "traumatología" in line


def test_the_note_across_the_handoff_tells_the_stage_its_first_move_and_not_the_cita(tc) -> None:
    """A stage handed the facts recites them; a stage handed the move looks them up."""
    previous = tc.prev_agent
    previous.errand = identify.CANCEL

    summary = previous.summary()

    assert "anularla" in summary
    assert "consultar su cita con tu herramienta" in summary
    assert "10:00" not in summary and "Irene Campos" not in summary


def test_the_same_identification_still_hands_a_rescheduling_the_hour_it_needs(tc) -> None:
    """The note is per errand: ChooseSlot is still told the cita it is about to move."""
    summary = tc.prev_agent.summary()

    assert "jueves 3 de septiembre a las 10:00" in summary


def test_cancel_appointment_is_irreversible_and_confirm_attendance_is_not() -> None:
    """Two verbs on one stage, and only one of them is a door the guard stands at."""
    catalog = project_module.PROJECT.tools

    assert catalog.get("cancel_appointment").side_effect is SideEffect.IRREVERSIBLE
    assert catalog.get("cancel_appointment").needs_confirmation() is True
    assert catalog.get("cancel_appointment").compensation is None
    assert catalog.get("confirm_attendance").side_effect is SideEffect.WRITE
    assert catalog.get("confirm_attendance").needs_confirmation() is False
    assert catalog.get("confirm_attendance").compensation == "rebook_slot"


def test_the_board_reads_a_cancelled_cita_as_gone_and_a_confirmed_one_as_touched() -> None:
    """Criterion of the card: `tone` is the clinic's call, and the console draws what it says."""
    agenda_module = importlib.import_module("tenants.clinica-norte.adapters.agenda")

    assert agenda_module.STATES["cancelled"] == ("cancelled", "gone")
    assert agenda_module.STATES["confirmed"] == ("confirmed", "changed")


def test_the_log_line_of_each_verb_names_the_cita_and_how_it_now_stands() -> None:
    agenda_module = importlib.import_module("tenants.clinica-norte.adapters.agenda")

    assert agenda_module.summarise_change({"appointment_id": ANA, "status": "cancelled"}) == (
        f"appointment {ANA} now cancelled"
    )
    assert agenda_module.summarise_change({"appointment_id": ANA, "status": "confirmed"}) == (
        f"appointment {ANA} now confirmed"
    )


@needs_llm
async def test_a_caller_who_wants_their_cita_gone_is_handed_to_the_stage_that_drops_it(tc) -> None:
    """The fourth exit of Identify, and it is a tool call in the run rather than a flag."""
    context = fake_context("clinica-norte", "reagendamiento")

    conversation = await run_conversation(
        context,
        ["buenos días, quería anular la cita que tengo", "Ana García Ruiz"],
    )

    conversation.results[-1].expect.contains_agent_handoff(new_agent_type=stages.CancelOrConfirm)
    assert context.customer["appointment_id"] == ANA


@needs_llm
async def test_a_yes_drops_the_cita_and_the_log_carries_the_consent_before_the_write(
    settling, tc
) -> None:
    """The errand end to end: look it up, read it back, take the yes, release the hour.

    The audit half is the half worth reading, and it is the same shape as the
    other three doors: `confirm.granted` naming `cancel_appointment` is on the
    log BEFORE the `tool.call` that dropped anything, and the freed hour is on
    offer the moment it lands.
    """
    agenda = tc.adapters["agenda"]

    await run_conversation(tc, ["sí, esa, quiero anularla", "sí, anúlemela"], settling)

    assert agenda.book[ANA]["status"] == "cancelled"
    kinds = [(event.kind, event.payload.get("tool")) for event in tc.log.events()]
    assert kinds.index(("confirm.granted", "cancel_appointment")) < kinds.index(
        ("tool.call", "cancel_appointment")
    )
    freed = await agenda.execute(
        "find_availability", {"date": "2026-09-03", "specialty": "traumatología"}
    )
    assert "sl-20260903-1000-trau" in [slot["id"] for slot in freed]


@needs_llm
async def test_a_caller_who_says_they_are_coming_has_it_written_down_in_one_step(
    settling, tc
) -> None:
    """No ConfirmTask on this one, on purpose: nothing is being taken from the patient."""
    tc.prev_agent.errand = identify.CONFIRM
    agenda = tc.adapters["agenda"]

    await run_conversation(tc, ["sí, esa misma, que voy a ir"], stages.CancelOrConfirm(tc))

    assert agenda.book[ANA]["status"] == "confirmed"
    assert agenda.book[ANA]["when"] == "2026-09-03T10:00", "a confirmation moves no hour"
    assert not [event for event in tc.log.events() if event.kind == "confirm.request"], (
        "a compensable write must not ask the caller for a second yes"
    )
