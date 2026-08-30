"""DeepEval ring 1 for the reception prompt: does every reply keep the reception line?

One GEval over every golden of the project, judged against the behaviour the
golden describes. The criterion, the judge and the threshold live in the
project's own `evals/metrics.py`, so this file only decides which turn to run
and what to judge — and the HTML report a reviewer opens scores the same runs
by the same rules.

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
    inputs = [] if golden.get("turn") == bridge.GREETING_TURN else [golden["input"]]
    conversation = await run_conversation(tc, inputs)
    case = bridge.test_case_for(golden, conversation, bridge.tool_descriptions(tc))

    assert_test(case, [metrics.reception_line()])
