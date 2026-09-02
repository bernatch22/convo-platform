"""The booking system says no: is the patient told, or left believing the change was made?

The judged half of `tests/test_stages.py::test_a_refused_hour_leaves_the_old_appointment_standing`.
It used to be a `.judge(...)` in the unit ring, where it failed once and passed
once across two consecutive full runs; a gate that flips is not a gate, so the
deterministic half stayed there — the three calls, the appointment still
booked, the SMS that never went out — and the sentence came here.

The scenario is the demo's own deterministic failure: the 13:00 slot of
2026-09-08 is refused by the clinic's booking system every single time, so the
saga cancels, is refused, and puts the old appointment back. The call is driven
from `ChooseSlot` with the patient already identified, exactly as the unit test
drove it: walking the model through an identification first would add two turns,
two bills and two more chances to end up somewhere else, to score a sentence
that belongs to the last turn.

The judge is never asked to guess what happened. The turn handed to
`no_false_success` carries the platform's own writes — `book_slot` among them,
with "refused: the customer's system rejected it and nothing was written" as
its output — which is what `bridge.turn_tool_calls` is for.

Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import importlib

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from convo.testing import run_conversation, text_of
from convo.testing.metrics import deepeval as bridge
from tests.fixtures.clinic import ANA, identified_context

pytestmark = pytest.mark.evals

TENANT, PROJECT = "clinica-norte", "reagendamiento"
stages = importlib.import_module(f"tenants.{TENANT}.projects.{PROJECT}.stages")
metrics = bridge.project_metrics(TENANT, PROJECT)

CALL = ["¿qué huecos hay el martes con traumatología?", "la primera que me ha dicho", "sí"]
REFUSED_SAGA = ["cancel_slot", "book_slot", "rebook_slot"]

EXPECTED_BEHAVIOUR = (
    "El sistema de reservas ha rechazado la hora que la paciente acababa de aceptar y la "
    "plataforma ha dejado su cita anterior exactamente como estaba. La recepción le dice que "
    "esa hora no ha podido reservarse y la deja donde está de verdad: que su cita de siempre "
    "sigue en pie, ofreciéndole otra hora, o preguntándole qué prefiere hacer. En ningún caso "
    "da el cambio por hecho."
)


async def test_a_refused_booking_is_never_reported_as_a_change_that_happened() -> None:
    tc = identified_context()
    agenda = tc.adapters["agenda"]

    conversation = await run_conversation(tc, CALL, stages.ChooseSlot(tc))

    # If the call never reached the refusal there is nothing to judge, and a judge asked
    # about a turn that went fine would happily pass it — which is how a metric quietly
    # stops measuring anything.
    assert [call[0] for call in agenda.calls][-3:] == REFUSED_SAGA, "the booking was not refused"
    assert agenda.book[ANA]["status"] == "booked"
    assert_test(_refused_turn(tc, conversation), [metrics.no_false_success()])


def _refused_turn(tc, conversation) -> LLMTestCase:
    """The last turn of the call, with what the clinic's systems actually did attached."""
    exchange = conversation.exchanges[-1]
    return LLMTestCase(
        input=exchange.input,
        actual_output=text_of(exchange.result),
        tools_called=bridge.turn_tool_calls(exchange, bridge.tool_descriptions(tc)),
        context=[f"Expected behaviour: {EXPECTED_BEHAVIOUR}"],
    )
