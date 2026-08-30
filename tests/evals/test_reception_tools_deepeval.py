"""DeepEval ring 1 for the agenda tool: does reception call it when it should, and with what?

Three questions per golden, one conversation to answer all three, because a
headless turn against real Haiku is the expensive part and running it once per
metric would triple the bill for the same evidence:

- ToolCorrectness, on all six — the agenda is consulted for the three goldens
  that name a day and left alone for the three that do not. It compares names
  only and asks no judge, so it is the cheap deterministic gate.
- the resolved date, on the three that call — `dates.resolve` turns whatever
  the model passed into a calendar day and it has to be the day the patient
  meant. This is an assertion, not a metric: there is exactly one right answer
  and a judge would only add variance to it.
- ArgumentCorrectness, on the same three — judged, for everything a literal
  comparison cannot see: a specialty invented, or one the patient stated and
  the model dropped.

Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import datetime
import importlib
import json
import pathlib

import pytest
from deepeval import assert_test

from core.testing import deepeval as bridge
from core.testing import fake_context, run_conversation

pytestmark = pytest.mark.evals

TENANT, PROJECT = "clinica-norte", "reagendamiento"
GOLDENS = pathlib.Path("tenants") / TENANT / "projects" / PROJECT / "evals" / "goldens.json"

dates = importlib.import_module(f"tenants.{TENANT}.projects.{PROJECT}.dates")
metrics = bridge.project_metrics(TENANT, PROJECT)


def load_goldens() -> list[dict]:
    """The project's goldens: an input, the behaviour expected, the tools expected."""
    return json.loads(GOLDENS.read_text())


async def run_golden(tc, golden: dict):
    """The conversation a golden produces: the opening line alone, or the turn it judges.

    A golden that judges a later stage replays the turns under `before` first —
    identifying the patient is what gets a rescheduling call as far as the
    agenda — and only the last turn is scored.
    """
    return await run_conversation(tc, bridge.inputs_for(golden))


@pytest.mark.parametrize("golden", load_goldens(), ids=lambda g: g["input"][:32])
async def test_the_agenda_is_consulted_exactly_when_the_golden_expects_it(golden: dict) -> None:
    tc = fake_context(TENANT, PROJECT)
    conversation = await run_golden(tc, golden)
    case = bridge.test_case_for(golden, conversation, bridge.tool_descriptions(tc))
    scored = [metrics.tool_correctness()]

    # A golden that expected a call and got none is ToolCorrectness's failure to
    # report, with its own reason: checking arguments that do not exist would
    # only bury it under an IndexError.
    if golden.get("expected_tools") and case.tools_called:
        said = case.tools_called[0].input_parameters.get("date")
        expected = datetime.date.fromisoformat(golden["expected_date"])
        assert said and dates.resolve(said, tc.today) == expected, (
            f"the model asked the agenda for {said!r}, which is not {expected}"
        )
        scored.append(metrics.argument_correctness())

    assert_test(case, scored)
