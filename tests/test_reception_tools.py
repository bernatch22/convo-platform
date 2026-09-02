"""Reading the agenda: the date language, the fake adapter, and the model's tool call.

Three rings in one file, cheapest first: `dates.resolve` and `FakeAgenda` are
pure and run in milliseconds; the last two tests put a real Claude Haiku in
front of the prompt and are skipped without a key.

The agenda belongs to the ChooseSlot stage from ms-3 on — a call reaches it once
the patient is identified — so the model tests start there instead of replaying
an identification whose behaviour is pinned in `tests/test_stages.py`.

Nothing here asks a judge anything. What the reply SAYS about the hours it was
given is scored in the evals ring, on the «¿qué turnos hay el jueves?» golden of
`tenants/clinica-norte/projects/reagendamiento/evals/goldens.json` — see the
note on `test_asking_for_thursday_calls_the_tool_with_the_day_the_patient_said`.
"""

import datetime
import importlib
import json

import pytest

from convo.testing import TODAY, fake_context, run_conversation
from tests.conftest import needs_llm
from tests.test_stages import identified_context

pytestmark = pytest.mark.unit

PROJECT = "tenants.clinica-norte.projects.reagendamiento"
dates = importlib.import_module(f"{PROJECT}.dates")
tools_module = importlib.import_module(f"{PROJECT}.tools")
agenda_module = importlib.import_module("tenants.clinica-norte.adapters.agenda")
stages = importlib.import_module(f"{PROJECT}.stages")
FakeAgenda = agenda_module.FakeAgenda

TUESDAY = TODAY  # 2026-09-01
THURSDAY = datetime.date(2026, 9, 3)
SUNDAY = datetime.date(2026, 9, 6)


@pytest.fixture
def tc():
    return fake_context("clinica-norte", "reagendamiento")


@pytest.fixture
def choosing():
    """The stage that owns the agenda, entered with the patient already identified."""
    context = identified_context()
    return context, stages.ChooseSlot(context)


# --- the date language ------------------------------------------------------


def test_a_weekday_resolves_to_the_next_one_still_to_come() -> None:
    assert dates.resolve("el jueves", TUESDAY) == THURSDAY
    assert dates.resolve("jueves", TUESDAY) == THURSDAY
    assert dates.resolve("El Jueves,", TUESDAY) == THURSDAY


def test_the_same_weekday_as_today_means_the_one_a_week_away() -> None:
    assert dates.resolve("martes", TUESDAY) == TUESDAY + datetime.timedelta(days=7)


def test_hoy_manana_and_pasado_manana_count_from_the_day_of_the_call() -> None:
    assert dates.resolve("hoy", TUESDAY) == TUESDAY
    assert dates.resolve("mañana", TUESDAY) == datetime.date(2026, 9, 2)
    assert dates.resolve("pasado mañana", TUESDAY) == THURSDAY


def test_next_week_alone_is_its_monday_and_with_a_weekday_is_that_day_of_it() -> None:
    assert dates.resolve("la semana que viene", TUESDAY) == datetime.date(2026, 9, 7)
    assert dates.resolve("el jueves de la semana que viene", TUESDAY) == datetime.date(2026, 9, 10)


def test_an_iso_date_is_taken_as_written() -> None:
    assert dates.resolve("2026-12-24", TUESDAY) == datetime.date(2026, 12, 24)


def test_an_expression_with_no_day_in_it_is_a_value_error() -> None:
    with pytest.raises(ValueError):
        dates.resolve("cuando pueda", TUESDAY)
    with pytest.raises(ValueError):
        dates.resolve("", TUESDAY)


def test_a_day_is_named_the_way_a_receptionist_says_it() -> None:
    assert dates.spanish_day(THURSDAY) == "jueves 3 de septiembre"
    assert dates.spanish_moment("2026-09-03T10:30") == "jueves 3 de septiembre a las 10:30"


# --- the fake agenda --------------------------------------------------------


async def test_the_agenda_answers_a_day_with_at_most_three_slots() -> None:
    slots = await FakeAgenda().execute("find_availability", {"date": THURSDAY.isoformat()})

    assert 1 <= len(slots) <= 3
    assert all(set(slot) == {"id", "when", "doctor"} for slot in slots)
    assert all(slot["when"].startswith("2026-09-03T") for slot in slots)


async def test_the_same_question_always_gets_the_same_answer() -> None:
    args = {"date": THURSDAY.isoformat(), "specialty": "traumatología"}

    first = await FakeAgenda().execute("find_availability", args)
    second = await FakeAgenda().execute("find_availability", args)

    assert first == second


async def test_a_specialty_is_answered_by_its_own_doctors() -> None:
    args = {"date": THURSDAY.isoformat(), "specialty": "traumatólogo"}

    slots = await FakeAgenda().execute("find_availability", args)

    assert all(slot["doctor"] in agenda_module.DOCTORS["traumatologia"] for slot in slots)


async def test_a_closed_day_has_no_slots_rather_than_an_error() -> None:
    slots = await FakeAgenda().execute("find_availability", {"date": SUNDAY.isoformat()})

    assert slots == []


async def test_a_date_the_agenda_cannot_read_is_a_value_error() -> None:
    with pytest.raises(ValueError):
        await FakeAgenda().execute("find_availability", {"date": "el jueves"})


def test_the_model_is_handed_two_hours_even_when_the_agenda_returns_three() -> None:
    slots = [
        {"id": "a", "when": "2026-09-03T09:00", "doctor": "Dr. Alberto Navarro"},
        {"id": "b", "when": "2026-09-03T14:00", "doctor": "Dra. Irene Campos"},
        {"id": "c", "when": "2026-09-03T17:00", "doctor": "Dr. Hugo Ferrer"},
    ]

    offer = tools_module._offer(THURSDAY, slots)

    assert offer.count("\n- ") == 2
    assert "Hugo Ferrer" not in offer
    assert tools_module.MORE_LEFT in offer


def test_a_day_with_nothing_free_says_so_instead_of_offering_nothing() -> None:
    assert tools_module._offer(THURSDAY, []) == "Sin huecos libres el jueves 3 de septiembre."


async def test_the_tool_reaches_the_adapter_through_the_platform_executor(tc) -> None:
    slots = await tc.tools.call("find_availability", {"date": THURSDAY.isoformat()})

    assert slots and slots[0]["when"].startswith("2026-09-03T")


# --- the model ---------------------------------------------------------------


@needs_llm
async def test_asking_for_thursday_calls_the_tool_with_the_day_the_patient_said(choosing) -> None:
    """The turn reaches the agenda, and with the day the patient named — not one it invented.

    Nothing about the SHAPE of the turn is asserted any more. Haiku usually
    opens with "Un momento, le consulto la agenda…" before calling, sometimes
    says nothing at all, and sometimes asks the agenda twice because the
    patient's appointment carries a specialty — all three are correct calls, and
    walking the events in order and demanding the call be the next one after a
    single skipped message failed a whole run for a politer answer. What must
    hold is that the agenda was asked at all, and that every day it was asked
    about, resolved against the frozen `today`, is the Thursday the patient said.

    Whether the reply then OFFERS those hours is a judgement, and a judgement
    does not belong in a gate that has to be green three runs out of three: the
    «¿qué turnos hay el jueves?» golden scores it in the evals ring, where
    `reception_line` reads it against the expected behaviour and
    `grounded_facts_dag` proves every hour came off the agenda.
    """
    tc, stage = choosing
    conversation = await run_conversation(tc, ["¿qué turnos hay el jueves?"], stage)

    days = _days_asked_of_the_agenda(conversation.results[0], tc.today)

    assert days, "the turn never reached the agenda"
    assert set(days) == {THURSDAY}, f"the agenda was asked about {days}, not {THURSDAY}"


@needs_llm
async def test_the_system_prompt_is_served_from_the_cache_on_the_second_turn(choosing) -> None:
    tc, stage = choosing
    conversation = await run_conversation(
        tc, ["hola, quería cambiar mi cita", "¿me dice qué hay el jueves?"], stage
    )

    assert conversation.cached_prompt_tokens() > 0, (
        "Haiku 4.5 caches prefixes of 4096+ tokens: a cache read of 0 means the prefix "
        "shrank below the floor or something in it changes between turns"
    )


def _days_asked_of_the_agenda(result, today: datetime.date) -> list[datetime.date]:
    """Every day `find_availability` was asked about in one turn, as calendar dates.

    The model passes the day in the patient's own words — that is what the tool
    documents — so the raw argument is read through `dates.resolve` before it is
    compared to anything.
    """
    return [
        dates.resolve(json.loads(event.item.arguments)["date"], today)
        for event in result.events
        if event.type == "function_call" and event.item.name == "find_availability"
    ]
