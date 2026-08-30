"""The three stages of a rescheduling call: identify, choose an hour, say goodbye.

Two rings, cheapest first. The adapters, the guard and the saga are
deterministic and run in milliseconds — they are where "nothing is booked
without a yes" is actually proved, because a refusal that depends on a model
changing its mind is not a guarantee. The tests at the bottom put a real Claude
Haiku in front of the prompts and walk the whole call; they are skipped without
a key.
"""

import importlib

import pytest

from core import confirm
from core.testing import fake_context, final_message, run_conversation, text_of
from core.tools.contract import SideEffect
from core.tools.guard import ToolRefused
from core.tools.saga import SagaFailed
from tests.conftest import needs_llm

pytestmark = pytest.mark.unit

PROJECT = "tenants.clinica-norte.projects.reagendamiento"
dates = importlib.import_module(f"{PROJECT}.dates")
project_module = importlib.import_module(f"{PROJECT}.project")
stages = importlib.import_module(f"{PROJECT}.stages")
choose_slot = importlib.import_module(f"{PROJECT}.stages.choose_slot")
tools_module = importlib.import_module(f"{PROJECT}.tools")
patients = importlib.import_module("tenants.clinica-norte.adapters.patients")

ANA = "ap-20260903-1000-trau"  # the seeded appointment every test reschedules
THURSDAY_11 = {"id": "sl-20260903-1100-trau", "when": "2026-09-03T11:00", "doctor": "Dra. Ruiz"}
REFUSED_13 = {"id": "sl-20260908-1300-trau", "when": "2026-09-08T13:00", "doctor": "Dra. Campos"}


@pytest.fixture
def tc():
    """A session that has already identified Ana García, which is where ChooseSlot begins."""
    return identified_context()


def identified_context():
    """A context past the Identify stage: the patient is found and her cita is known.

    `prev_agent` matters as much as `customer`: what ChooseSlot knows about the
    caller arrives as the previous stage's `summary()` in its `on_enter`, and a
    stage entered without one asks for the name again — which is the right
    behaviour and the wrong test. Shared with `tests/test_reception_tools.py`,
    which reads the agenda from this same stage.
    """
    context = fake_context("clinica-norte", "reagendamiento")
    context.customer = {"appointment_id": ANA, **context.adapters["agenda"].book[ANA]}
    context.prev_agent = stages.Identify(context)
    return context


def choosing(tc) -> stages.ChooseSlot:
    """The ChooseSlot stage entered the way a real call enters it: after an identification."""
    return stages.ChooseSlot(tc)


def booking_args(tc, slot: dict[str, str]) -> dict[str, str]:
    return choose_slot._booking_args(tc, slot)


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
        "cancel_slot",
        "find_availability",
        "find_patient",
        "rebook_slot",
        "send_sms",
    ]
    assert catalog.get("book_slot").side_effect is SideEffect.IRREVERSIBLE
    assert catalog.get("book_slot").needs_confirmation() is True
    assert catalog.get("cancel_slot").compensation == "rebook_slot"
    assert catalog.get("find_availability").needs_confirmation() is False


# --- what each stage says to the next ---------------------------------------


def test_the_hour_the_caller_says_is_matched_however_they_say_it() -> None:
    assert choose_slot._normalise_hour("11:00") == "11:00"
    assert choose_slot._normalise_hour("9") == "09:00"
    assert choose_slot._normalise_hour("las 16.30") == "16:30"
    assert choose_slot._normalise_hour("a media tarde") == ""


def test_the_confirmation_sentence_says_the_hour_the_way_a_person_says_it() -> None:
    """It is read out verbatim, so «13:00» would be spoken «las trece cero cero»."""
    said = tools_module.confirmation_question(REFUSED_13)

    assert said == "martes 8 de septiembre a la una de la tarde con Dra. Campos, ¿lo confirmo?"


def test_identify_hands_the_next_stage_the_patient_and_the_cita_they_already_have(tc) -> None:
    summary = stages.Identify(tc).summary()

    assert "Ana García Ruiz" in summary
    assert "jueves 3 de septiembre a las 10:00" in summary


def test_choose_slot_hands_the_farewell_the_appointment_that_now_exists(tc) -> None:
    stage = choosing(tc)
    assert "Todavía no" in stage.summary()

    stage.booked = THURSDAY_11
    assert "jueves 3 de septiembre a las 11:00" in stage.summary()


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
async def test_a_refused_hour_leaves_the_old_appointment_standing(tc, judge_llm) -> None:
    """The 13:00 slot of 2026-09-08 is always refused; the caller must be told the truth."""
    agenda, sms = tc.adapters["agenda"], tc.adapters["sms"]

    conversation = await run_conversation(
        tc,
        ["¿qué huecos hay el martes con traumatología?", "la primera que me ha dicho", "sí"],
        choosing(tc),
    )

    assert [c[0] for c in agenda.calls][-3:] == ["cancel_slot", "book_slot", "rebook_slot"]
    assert agenda.book[ANA]["status"] == "booked"
    assert sms.sent == []
    await final_message(conversation.results[2]).judge(
        judge_llm,
        intent="dice que no ha podido reservarse esa hora y que la cita anterior del paciente "
        "sigue en pie, y le ofrece otra hora; no dice en ningún caso que el cambio esté hecho",
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
