"""Reception reads the agenda: the date language, the fake adapter, and the model's first tool call.

Three rings in one file, cheapest first: `dates.resolve` and `FakeAgenda` are
pure and run in milliseconds; the last three tests put a real Claude Haiku in
front of the prompt and are skipped without a key.
"""

import datetime
import importlib
import json

import pytest

from core.testing import TODAY, fake_context, run_conversation
from tests.conftest import needs_llm

pytestmark = pytest.mark.unit

PROJECT = "tenants.clinica-norte.projects.reagendamiento"
dates = importlib.import_module(f"{PROJECT}.dates")
agenda_module = importlib.import_module("tenants.clinica-norte.adapters.agenda")
FakeAgenda = agenda_module.FakeAgenda

TUESDAY = TODAY  # 2026-09-01
THURSDAY = datetime.date(2026, 9, 3)
SUNDAY = datetime.date(2026, 9, 6)


@pytest.fixture
def tc():
    return fake_context("clinica-norte", "reagendamiento")


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


async def test_the_tool_reaches_the_adapter_through_the_platform_executor(tc) -> None:
    slots = await tc.tools.call("find_availability", {"date": THURSDAY.isoformat()})

    assert slots and slots[0]["when"].startswith("2026-09-03T")


# --- the model ---------------------------------------------------------------


@needs_llm
async def test_asking_for_thursday_calls_the_tool_with_the_day_the_patient_said(tc) -> None:
    conversation = await run_conversation(tc, ["¿qué turnos hay el jueves?"])

    call = conversation.results[0].expect.next_event().is_function_call(name="find_availability")
    said = call.event().item.arguments
    assert dates.resolve(_argument(said, "date"), tc.today) == THURSDAY


@needs_llm
async def test_the_reply_offers_the_hours_the_agenda_returned(tc, judge_llm) -> None:
    conversation = await run_conversation(tc, ["¿qué turnos hay el jueves?"])

    message = conversation.results[0].expect.contains_message(role="assistant")
    await message.judge(
        judge_llm,
        intent="ofrece al menos una hora concreta para el jueves y pregunta cuál prefiere el "
        "paciente, sin inventar que va a llamar más tarde para comprobarlo",
    )


@needs_llm
async def test_the_system_prompt_is_served_from_the_cache_on_the_second_turn(tc) -> None:
    conversation = await run_conversation(
        tc, ["hola, quería cambiar mi cita", "¿qué turnos hay el jueves?"]
    )

    assert conversation.cached_prompt_tokens() > 0, (
        "Haiku 4.5 caches prefixes of 4096+ tokens: a cache read of 0 means the prefix "
        "shrank below the floor or something in it changes between turns"
    )


def _argument(raw: str, name: str) -> str:
    """One argument out of the JSON the model produced for a function call."""
    return json.loads(raw)[name]
