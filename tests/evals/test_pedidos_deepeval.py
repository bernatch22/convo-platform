"""DeepEval ring 1 for Tienda Sur's order desk: does every reply keep the line, and hold up?

Four metrics over every golden of the project, from ONE conversation per
golden, because a headless turn against real Haiku is the expensive part and
running it once per metric would multiply the bill for the same evidence. The
clinic pays that bill twice today (its GEval suite and its tool suite each run
their own conversations); this file is what that lesson looks like written down.

The order the metrics run in is the order of what they cost:

- `grounded_facts_dag` and `keeps_the_register` first: both are decided in
  code and cost nothing at all unless something is actually wrong. The register
  one is the whole argument of ms-5 in a single assertion — the same graph
  builder that fails the clinic for a "te" fails this shop for an "usted".
- `tool_correctness`, deterministic too: the order system is consulted for the
  goldens that name a pedido and left alone for the four that do not.
- `order_desk_line`, the GEval, on tone, register, length and remit — one judge
  call, and the only one in the file.

Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import json
import pathlib

import pytest
from deepeval import assert_test

from core.testing import deepeval as bridge
from core.testing import fake_context, run_conversation

pytestmark = pytest.mark.evals

TENANT, PROJECT = "tienda-sur", "pedidos"
GOLDENS = pathlib.Path("tenants") / TENANT / "projects" / PROJECT / "evals" / "goldens.json"

metrics = bridge.project_metrics(TENANT, PROJECT)


def load_goldens() -> list[dict]:
    """The project's goldens: an input, the behaviour expected, the tools expected."""
    return json.loads(GOLDENS.read_text())


@pytest.mark.parametrize("golden", load_goldens(), ids=lambda g: g["input"][:32])
async def test_the_order_desk_keeps_its_line(golden: dict) -> None:
    tc = fake_context(TENANT, PROJECT)
    conversation = await run_conversation(tc, bridge.inputs_for(golden))
    descriptions = bridge.tool_descriptions(tc)

    whole_call = bridge.conversational_test_case_for(
        conversation, descriptions, scenario=golden["expected_behaviour"], name=golden["input"]
    )
    assert_test(whole_call, [metrics.grounded_facts_dag(), metrics.keeps_the_register()])
    turn = bridge.test_case_for(golden, conversation, descriptions)
    assert_test(turn, [*tools_of(golden), metrics.order_desk_line()])


def tools_of(golden: dict) -> list:
    """ToolCorrectness, unless the golden declares no `expected_tools` at all.

    An empty list is an expectation — "this turn must call nothing" — and three
    goldens live off it. A MISSING key is the other thing: a turn where two
    behaviours are both correct. The shipped-order golden is the one, and it is
    honest about it: the agent may call the cancellation tool and read the
    refusal off it, or answer from the status it read seconds earlier in the
    same stage. Neither cancels anything, and pinning either would fail a build
    for a defensible reply. What that golden is really about is the words, and
    `order_desk_line` and `grounded_facts_dag` still score them.
    """
    return [metrics.tool_correctness()] if "expected_tools" in golden else []
