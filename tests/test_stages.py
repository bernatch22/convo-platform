"""The stages of a call to the clinic: identify, move an hour or ask for a first one, close.

Two rings, cheapest first. The adapters, the guard and the saga are
deterministic and run in milliseconds — they are where "nothing is booked
without a yes" is actually proved, because a refusal that depends on a model
changing its mind is not a guarantee. The tests at the bottom put a real Claude
Haiku in front of the prompts and walk the whole call; they are skipped without
a key.

They assert facts and never opinions: which tools ran, in what order, what the
agenda holds afterwards, whether an SMS went out. Nothing in this file asks a
judge whether a sentence was good enough — that question belongs to the evals
ring, where a flip costs a re-run and not a red build.
"""

import importlib

import pytest

from core import confirm
from core.testing import fake_context, run_conversation, text_of
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
new_booking = importlib.import_module(f"{PROJECT}.stages.new_booking")
tools_module = importlib.import_module(f"{PROJECT}.tools")
patients = importlib.import_module("tenants.clinica-norte.adapters.patients")

ANA = "ap-20260903-1000-trau"  # the seeded appointment every test reschedules
THURSDAY_11 = {"id": "sl-20260903-1100-trau", "when": "2026-09-03T11:00", "doctor": "Dra. Ruiz"}
REFUSED_13 = {"id": "sl-20260908-1300-trau", "when": "2026-09-08T13:00", "doctor": "Dra. Campos"}
PEDRO = {"patient": "Pedro Ramos Gil", "phone": "699000000"}  # nobody the book has ever held


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


@pytest.fixture
def unknown():
    """A session past Identify for somebody with NO cita: exactly where NewBooking begins.

    `customer` carries a name and a phone and no `appointment_id` — which is the
    whole difference between the two booking stages, and the thing `Identify`
    writes when the caller asks for a first appointment.
    """
    context = fake_context("clinica-norte", "reagendamiento")
    context.customer = dict(PEDRO)
    context.prev_agent = stages.Identify(context)
    return context


def booking(tc) -> stages.NewBooking:
    """The NewBooking stage entered the way a real call enters it: after an identification."""
    return stages.NewBooking(tc)


def new_booking_args(tc, slot: dict[str, str], specialty: str = "traumatología") -> dict[str, str]:
    return new_booking._booking_args(tc, slot, specialty)


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
        "create_appointment",
        "find_availability",
        "find_patient",
        "rebook_slot",
        "send_sms",
    ]
    assert catalog.get("book_slot").side_effect is SideEffect.IRREVERSIBLE
    assert catalog.get("book_slot").needs_confirmation() is True
    assert catalog.get("create_appointment").side_effect is SideEffect.IRREVERSIBLE
    assert catalog.get("create_appointment").needs_confirmation() is True
    assert catalog.get("create_appointment").compensation == "cancel_slot"
    assert catalog.get("cancel_slot").compensation == "rebook_slot"
    assert catalog.get("find_availability").needs_confirmation() is False


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
    said = tools_module.new_confirmation_question(THURSDAY_11)

    assert said == "jueves 3 de septiembre a las once de la mañana con Dra. Ruiz, ¿se la reservo?"


# --- what each stage says to the next ---------------------------------------


def test_the_hour_the_caller_says_is_matched_however_they_say_it() -> None:
    """Shared by both booking stages, which is why it lives in `tools` and not in either."""
    assert tools_module.normalise_hour("11:00") == "11:00"
    assert tools_module.normalise_hour("9") == "09:00"
    assert tools_module.normalise_hour("las 16.30") == "16:30"
    assert tools_module.normalise_hour("a media tarde") == ""
    assert tools_module.hour_of("2026-09-03T11:00") == "11:00"


def test_the_confirmation_sentence_says_the_hour_the_way_a_person_says_it() -> None:
    """It is read out verbatim, so «13:00» would be spoken «las trece cero cero»."""
    said = tools_module.confirmation_question(REFUSED_13)

    assert said == "martes 8 de septiembre a la una de la tarde con Dra. Campos, ¿lo confirmo?"


def test_identify_hands_the_next_stage_the_patient_and_the_cita_they_already_have(tc) -> None:
    summary = stages.Identify(tc).summary()

    assert "Ana García Ruiz" in summary
    assert "jueves 3 de septiembre a las 10:00" in summary


def test_identify_tells_the_next_stage_when_the_caller_has_no_cita_at_all(unknown) -> None:
    """The one sentence that sends NewBooking down its own path instead of ChooseSlot's."""
    summary = stages.Identify(unknown).summary()

    assert "Pedro Ramos Gil" in summary
    assert "No consta ninguna cita" in summary


def test_new_booking_hands_the_farewell_the_cita_it_has_just_created(unknown) -> None:
    stage = booking(unknown)
    assert "Todavía no" in stage.summary()

    stage.booked = THURSDAY_11
    assert "jueves 3 de septiembre a las 11:00" in stage.summary()


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
