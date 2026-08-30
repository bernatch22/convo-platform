"""DeepEval ring 1 for the reception prompt: does every reply keep the reception line?

Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY). The judge is
Claude Haiku; the HTML report lands under reports/deepeval/.
"""

import json
import os
import pathlib

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.models import AnthropicModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

from core.testing import fake_context, run_conversation, text_of

pytestmark = pytest.mark.evals

GOLDENS = pathlib.Path("tenants/clinica-norte/projects/reagendamiento/evals/goldens.json")
JUDGE_MODEL = os.getenv("DEEPEVAL_JUDGE_MODEL", "claude-haiku-4-5")


async def actual_output(tc, golden: dict) -> str:
    """The text the golden judges: the opening line for `turn: greeting`, else the reply."""
    if golden.get("turn") == "greeting":
        return (await run_conversation(tc, [])).greeting
    conversation = await run_conversation(tc, [golden["input"]])
    return text_of(conversation.results[0])


def load_goldens() -> list[dict]:
    """The project's goldens: an input and the behaviour a reviewer expects."""
    return json.loads(GOLDENS.read_text())


def reception_line_metric() -> GEval:
    """Does the reply sound like Clínica Norte's reception and stay within its remit?"""
    return GEval(
        name="Reception line",
        criteria=(
            "The reply is what a phone receptionist of Clínica Norte (Madrid) would say: "
            "Spanish from Spain using 'usted', polite and warm, two or three short sentences, "
            "ends with one question or a concrete next step, stays on appointments and clinic "
            "information, never invents availability or clinical advice. Judge against the "
            "expected behaviour given in the input context."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
        ],
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=0.7,
    )


@pytest.mark.parametrize("golden", load_goldens(), ids=lambda g: g["input"][:32])
async def test_reception_keeps_its_line(golden: dict) -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    case = LLMTestCase(
        input=golden["input"],
        actual_output=await actual_output(tc, golden),
        context=[f"Expected behaviour: {golden['expected_behaviour']}"],
    )
    assert_test(case, [reception_line_metric()])
