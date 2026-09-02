"""The stages of a call to the clinic: identify, move an hour, ask for a first one, fix a number.

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
import inspect
from types import SimpleNamespace

import pytest

from convo.domain.tools import SideEffect
from convo.testing import fake_context, run_conversation, text_of
from convo.tools import confirm
from convo.tools.guard import ToolRefused
from convo.tools.saga import SagaFailed
from tests.conftest import needs_llm

pytestmark = pytest.mark.unit

PROJECT = "tenants.clinica-norte.projects.reagendamiento"
project_module = importlib.import_module(f"{PROJECT}.project")
stages = importlib.import_module(f"{PROJECT}.stages")
choose_slot = importlib.import_module(f"{PROJECT}.stages.choose_slot")
new_booking = importlib.import_module(f"{PROJECT}.stages.new_booking")
update_contact = importlib.import_module(f"{PROJECT}.stages.update_contact")
cancel_or_confirm = importlib.import_module(f"{PROJECT}.stages.cancel_or_confirm")
identify = importlib.import_module(f"{PROJECT}.stages.identify")
helpers_module = importlib.import_module(f"{PROJECT}.helpers")
messages_module = importlib.import_module(f"{PROJECT}.messages")
patients = importlib.import_module("tenants.clinica-norte.adapters.patients")

ANA = "ap-20260903-1000-trau"  # the seeded appointment every test reschedules
THURSDAY_11 = {"id": "sl-20260903-1100-trau", "when": "2026-09-03T11:00", "doctor": "Dra. Ruiz"}
REFUSED_13 = {"id": "sl-20260908-1300-trau", "when": "2026-09-08T13:00", "doctor": "Dra. Campos"}
PEDRO = {"patient": "Pedro Ramos Gil", "phone": "699000000"}  # nobody the book has ever held
NEW_NUMBER = "689000111"  # what Ana moves to; the 600-block one she leaves is 600123456


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


@pytest.fixture
def settling(tc):
    """A session that reached CancelOrConfirm: Ana identified, the errand a cancellation.

    `Identify.errand` again, and again it is not decoration: it is what makes the
    note this stage inherits tell it to look the cita up instead of reciting one,
    which is the rule the whole stage is built on.
    """
    tc.prev_agent.errand = identify.CANCEL
    return stages.CancelOrConfirm(tc)


@pytest.fixture
def changing(tc):
    """A session that reached UpdateContact: Ana identified, and the errand a data change.

    `Identify.errand` is not decoration. It is what makes the summary this stage
    inherits carry the phone number masked, which is the safeguard the errand is
    built on — so a fixture that skipped it would be testing a stage no call can
    produce.
    """
    tc.prev_agent.errand = identify.CONTACT
    return stages.UpdateContact(tc)


def contact_args(tc, phone: str = NEW_NUMBER) -> dict[str, str]:
    return update_contact._contact_args(tc, phone)


def _arguments(tool) -> list[str]:
    """The parameters a stage tool exposes to the model, ctx aside — its whole reach."""
    signature = inspect.signature(getattr(tool, "__func__", tool))
    return [name for name in signature.parameters if name not in ("self", "ctx")]


def run_context(tc):
    """The one thing a stage tool reads off its RunContext, and nothing else.

    A real `RunContext` belongs to a running session; these tests call the tool
    directly because what they pin is the refusal, which happens before any model
    is involved. `userdata` is the whole of the contract they need.
    """
    return SimpleNamespace(userdata=tc)


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


# --- what each stage says to the next ---------------------------------------


def test_the_hour_the_caller_says_is_matched_however_they_say_it() -> None:
    """Shared by both booking stages, which is why it lives in `tools` and not in either."""
    assert helpers_module.normalise_hour("11:00") == "11:00"
    assert helpers_module.normalise_hour("9") == "09:00"
    assert helpers_module.normalise_hour("las 16.30") == "16:30"
    assert helpers_module.normalise_hour("a media tarde") == ""
    assert helpers_module.hour_of("2026-09-03T11:00") == "11:00"


def test_the_confirmation_sentence_says_the_hour_the_way_a_person_says_it() -> None:
    """It is read out verbatim, so «13:00» would be spoken «las trece cero cero»."""
    said = helpers_module.confirmation_question(REFUSED_13)

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
