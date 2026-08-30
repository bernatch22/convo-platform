"""DeepEval ring 1 for the reception prompt: does every reply keep the line, and hold up?

Two metrics over every golden of the project, from one conversation, because a
headless turn against real Haiku is the expensive part:

- `grounded_facts_dag`, first, because it is deterministic and free in the
  normal case: code pulls every hour, price, name, phone and address out of
  what the agent said and matches it against the clinic's sheet, what the
  caller said and what the tools returned. A judge is paid only for what is
  left over, and only ever sees that claim next to the evidence.
- `reception_line`, the GEval, on tone, register, length and remit. It used to
  own the invention rule as well and flipped the price golden between 0.0 and
  0.9 across runs; the rule moved to the DAG and the criterion lost the clause.

The criteria, the judge and the thresholds live in the project's own
`evals/metrics.py`, so this file only decides which turn to run and what to
judge — and the HTML report a reviewer opens scores the same runs by the same
rules.

The greeting golden judges the opening line the agent produces in `on_enter`,
never a mid-conversation reply: the agent introduces itself once, and asking it
to do so again is asking for a behaviour a real call should not have. Every
other golden judges the WHOLE turn, filler included, because "un momento, le
consulto la agenda" and the answer that follows are one thing to the caller.

Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import json
import pathlib

import pytest
from deepeval import assert_test

from core.testing import deepeval as bridge
from core.testing import fake_context, run_conversation

pytestmark = pytest.mark.evals

TENANT, PROJECT = "clinica-norte", "reagendamiento"
GOLDENS = pathlib.Path("tenants") / TENANT / "projects" / PROJECT / "evals" / "goldens.json"

metrics = bridge.project_metrics(TENANT, PROJECT)


def load_goldens() -> list[dict]:
    """The project's goldens: an input and the behaviour a reviewer expects."""
    return json.loads(GOLDENS.read_text())


@pytest.mark.parametrize("golden", load_goldens(), ids=lambda g: g["input"][:32])
async def test_reception_keeps_its_line(golden: dict) -> None:
    tc = fake_context(TENANT, PROJECT)
    conversation = await run_conversation(tc, bridge.inputs_for(golden))
    descriptions = bridge.tool_descriptions(tc)

    grounded = bridge.conversational_test_case_for(
        conversation, descriptions, scenario=golden["expected_behaviour"], name=golden["input"]
    )
    assert_test(grounded, [metrics.grounded_facts_dag()])
    line = bridge.test_case_for(golden, conversation, descriptions)
    assert_test(line, [metrics.reception_line()])
