"""The model on the line: handoffs, consent and the cache, one real call per test."""

import pytest

from convo.testing import fake_context, run_conversation, text_of
from tests.conftest import needs_llm
from tests.fixtures.clinic import (  # noqa: F401  (fixtures)
    ANA,
    NEW_NUMBER,
    PEDRO,
    booking,
    changing,
    choosing,
    stages,
    tc,
    unknown,
)

pytestmark = pytest.mark.unit


# --- the model --------------------------------------------------------------


@needs_llm
async def test_identifying_the_patient_hands_the_call_over_to_choose_slot() -> None:
    """The transition is an event in the run, not a flag: the test can see it happen."""
    context = fake_context("clinica-norte", "reagendamiento")

    conversation = await run_conversation(
        context, ["hola, quería cambiar mi cita", "Ana García Ruiz, teléfono 600123456"]
    )

    conversation.results[1].expect.contains_agent_handoff(new_agent_type=stages.ChooseSlot)
    assert context.customer["appointment_id"] == ANA


@needs_llm
async def test_nothing_reaches_the_booking_system_until_the_caller_says_yes(tc) -> None:
    """The caller picks an hour, is read it back, and changes their mind: nothing was written."""
    agenda, sms = tc.adapters["agenda"], tc.adapters["sms"]

    conversation = await run_conversation(
        tc,
        ["¿qué huecos hay el jueves?", "la primera que me ha dicho", "no, espere, mejor lo dejo"],
        choosing(tc),
    )

    assert [c[0] for c in agenda.calls] == ["find_availability"], "book_slot ran without a yes"
    assert agenda.book[ANA].get("status") != "cancelled"
    assert sms.sent == []
    assert "confirmo" in conversation.reply(1), "the platform reads the hour back itself"


@needs_llm
async def test_a_yes_books_the_hour_and_writes_to_the_patient(tc) -> None:
    agenda, sms = tc.adapters["agenda"], tc.adapters["sms"]

    await run_conversation(
        tc,
        ["¿qué huecos hay el jueves?", "la primera que me ha dicho", "sí, confirmo"],
        choosing(tc),
    )

    assert [c[0] for c in agenda.calls] == ["find_availability", "cancel_slot", "book_slot"]
    assert agenda.book[ANA]["status"] == "cancelled"
    assert len(sms.sent) == 1 and sms.sent[0]["to"] == "600123456"


@needs_llm
async def test_a_refused_hour_leaves_the_old_appointment_standing(tc) -> None:
    """The 13:00 slot of 2026-09-08 is always refused: the saga compensates and nobody is told.

    What this test owns is the STATE after the refusal — the three calls in
    order, the appointment still standing, no SMS — and all three are facts a
    reader can check without asking anybody's opinion. What the receptionist
    then SAYS to the patient is the other half of the same defect, and it used
    to be judged right here; it failed once and passed once across two
    consecutive full runs, which is what a coin flip in a gate looks like. It
    now lives in `tests/evals/test_refused_booking_deepeval.py`, scored by the
    project's `no_false_success` metric with the refused write in front of the
    judge as evidence.
    """
    agenda, sms = tc.adapters["agenda"], tc.adapters["sms"]

    await run_conversation(
        tc,
        ["¿qué huecos hay el martes con traumatología?", "la primera que me ha dicho", "sí"],
        choosing(tc),
    )

    assert [c[0] for c in agenda.calls][-3:] == ["cancel_slot", "book_slot", "rebook_slot"]
    assert agenda.book[ANA]["status"] == "booked"
    assert sms.sent == []


@needs_llm
async def test_a_caller_with_no_cita_is_handed_over_to_the_stage_that_creates_one() -> None:
    """The miss asks again; the caller saying yes to a new one is what moves the call."""
    context = fake_context("clinica-norte", "reagendamiento")

    conversation = await run_conversation(
        context,
        [
            "hola, quería pedir cita, no tengo ninguna todavía",
            "Pedro Ramos Gil, teléfono 699000000",
        ],
    )

    conversation.results[-1].expect.contains_agent_handoff(new_agent_type=stages.NewBooking)
    assert context.customer == {"patient": "Pedro Ramos Gil", "phone": "699000000"}


@needs_llm
async def test_a_yes_creates_the_cita_and_writes_to_a_patient_who_had_none(unknown) -> None:
    agenda, sms = unknown.adapters["agenda"], unknown.adapters["sms"]

    await run_conversation(
        unknown,
        [
            "para traumatología, ¿qué tiene el jueves?",
            "la primera que me ha dicho",
            "sí, confirmo",
        ],
        booking(unknown),
    )

    assert [c[0] for c in agenda.calls] == ["find_availability", "create_appointment"]
    assert agenda.booked()[0]["patient"] == PEDRO["patient"]
    assert len(sms.sent) == 1 and sms.sent[0]["to"] == PEDRO["phone"]

    # The audit half of the same call: the yes is on the log before the write, and the
    # write left the one line its ToolSpec's `result_summary` renders — which is what
    # puts a created cita on the operator's outcomes board without a second mechanism.
    kinds = [(event.kind, event.payload.get("tool")) for event in unknown.log.events()]
    assert kinds.index(("confirm.granted", "create_appointment")) < kinds.index(
        ("tool.call", "create_appointment")
    )
    written = next(
        event
        for event in unknown.log.events()
        if event.kind == "tool.result" and event.payload.get("tool") == "create_appointment"
    )
    assert written.payload["summary"].startswith("appointment ap-")


@needs_llm
async def test_nothing_is_created_until_the_new_patient_says_yes(unknown) -> None:
    agenda, sms = unknown.adapters["agenda"], unknown.adapters["sms"]

    conversation = await run_conversation(
        unknown,
        ["para traumatología, ¿qué tiene el jueves?", "la primera", "no, espere, mejor lo dejo"],
        booking(unknown),
    )

    assert [c[0] for c in agenda.calls] == ["find_availability"], "it wrote without a yes"
    assert agenda.booked() == []
    assert sms.sent == []
    assert "reservo" in conversation.reply(1), "the platform reads the hour back itself"


@needs_llm
async def test_the_new_booking_prompt_is_served_from_the_cache_on_its_second_turn(
    unknown,
) -> None:
    conversation = await run_conversation(
        unknown, ["¿qué tiene el jueves?", "¿y el viernes?"], booking(unknown)
    )

    assert text_of(conversation.results[1])
    assert conversation.cached_prompt_tokens() > 0, (
        "Haiku 4.5 caches prefixes of 4096+ tokens: a cache read of 0 means this stage's "
        "prefix shrank below the floor or something in it changes between turns"
    )


@needs_llm
async def test_the_choose_slot_prompt_is_served_from_the_cache_on_its_second_turn(tc) -> None:
    conversation = await run_conversation(
        tc, ["¿qué huecos hay el jueves?", "¿y el viernes?"], choosing(tc)
    )

    assert text_of(conversation.results[1])
    assert conversation.cached_prompt_tokens() > 0, (
        "Haiku 4.5 caches prefixes of 4096+ tokens: a cache read of 0 means this stage's "
        "prefix shrank below the floor or something in it changes between turns"
    )


@needs_llm
async def test_a_caller_who_wants_their_number_changed_is_handed_to_the_stage_that_changes_it(
    tc,
) -> None:
    """The third exit of Identify, and it is a tool call in the run rather than a flag."""
    context = fake_context("clinica-norte", "reagendamiento")

    conversation = await run_conversation(
        context,
        ["hola, quería cambiar mi teléfono, el que tenéis está mal", "Ana García Ruiz"],
    )

    conversation.results[-1].expect.contains_agent_handoff(new_agent_type=stages.UpdateContact)
    assert context.customer["appointment_id"] == ANA


@needs_llm
async def test_a_yes_changes_the_number_and_the_log_carries_the_consent_before_the_write(
    changing, tc
) -> None:
    """The whole errand end to end: validate masked, take the new number, write it on a yes.

    The audit half is the half worth reading. The caller's yes is a
    `confirm.granted` line naming `update_contact`, it is on the log BEFORE the
    `tool.call` that changed anything, and the `tool.result` line carries the one
    sentence this write's `result_summary` renders — three digits, never the
    number. That is what puts a data change on the operator's board with no
    second mechanism.
    """
    agenda = tc.adapters["agenda"]

    conversation = await run_conversation(
        tc,
        ["sí, ese mismo", "el nuevo es el 689 000 111", "sí, cámbiemelo"],
        changing,
    )

    assert agenda.book[ANA]["phone"] == NEW_NUMBER
    assert [call[0] for call in agenda.calls] == ["update_contact"]
    assert agenda.book[ANA]["when"] == "2026-09-03T10:00", "a data change moves no hour"

    kinds = [(event.kind, event.payload.get("tool")) for event in tc.log.events()]
    assert kinds.index(("confirm.granted", "update_contact")) < kinds.index(
        ("tool.call", "update_contact")
    )
    written = next(
        event
        for event in tc.log.events()
        if event.kind == "tool.result" and event.payload.get("tool") == "update_contact"
    )
    assert written.payload["summary"].endswith("ending 111")
    assert NEW_NUMBER not in written.payload["summary"]
    assert "600123456" not in " ".join(conversation.reply(n) for n in range(3)), (
        "the number on file is validated by its last digits and never read out"
    )


@needs_llm
async def test_nothing_is_written_when_the_caller_backs_out_of_the_new_number(changing, tc) -> None:
    agenda = tc.adapters["agenda"]

    conversation = await run_conversation(
        tc,
        ["sí, ese mismo", "el nuevo es el 689 000 111", "no, espere, mejor lo dejo"],
        changing,
    )

    assert agenda.calls == [], "it changed a number without a yes"
    assert agenda.book[ANA]["phone"] == "600123456"
    assert "689 000 111" in conversation.reply(1), "the platform reads the number back itself"


@needs_llm
async def test_the_contact_prompt_is_served_from_the_cache_on_its_second_turn(changing, tc) -> None:
    """The third stage pays for its prefix once too, and neither turn here writes anything."""
    conversation = await run_conversation(
        tc,
        ["¿y cuál es el número que tenéis apuntado?", "¿y si me paso por recepción?"],
        changing,
    )

    assert text_of(conversation.results[1])
    assert conversation.cached_prompt_tokens() > 0, (
        "Haiku 4.5 caches prefixes of 4096+ tokens: a cache read of 0 means this stage's "
        "prefix shrank below the floor or something in it changes between turns"
    )
    assert conversation.cached_prompt_tokens() > 0, (
        "Haiku 4.5 caches prefixes of 4096+ tokens: a cache read of 0 means this stage's "
        "prefix shrank below the floor or something in it changes between turns"
    )
    assert tc.adapters["agenda"].calls == [], "neither turn asks for anything to be written"
