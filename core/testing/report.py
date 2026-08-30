"""Produce the DeepEval HTML report for a project's goldens.

`deepeval test run` is the CI gate (pass/fail); this module is the reviewer's
view: it runs the same goldens through `evaluate()` and writes a self-contained
HTML under tmp/reports/deepeval/. Usage:

    uv run python -m core.testing.report clinica-norte reagendamiento
"""

import asyncio
import json
import pathlib
import sys

from deepeval import evaluate
from deepeval.evaluate.configs import DisplayConfig
from deepeval.metrics import GEval
from deepeval.models import AnthropicModel
from deepeval.test_case import LLMTestCase, SingleTurnParams
from dotenv import load_dotenv

from core.testing.harness import fake_context, run_conversation, text_of

REPORT_DIR = pathlib.Path("tmp/reports/deepeval")  # generated artifact, not versioned


def reception_line_metric(judge_model: str = "claude-haiku-4-5") -> GEval:
    """Same criterion as tests/evals: does the reply keep the reception line?"""
    return GEval(
        name="Reception line",
        criteria=(
            "The reply is what a phone receptionist of Clínica Norte (Madrid) would say: "
            "Spanish from Spain using 'usted', polite and warm, two or three short sentences, "
            "ends with one question or a concrete next step, stays on appointments and clinic "
            "information, never invents availability or clinical advice. Judge against the "
            "expected behaviour given in the context."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
        ],
        model=AnthropicModel(model=judge_model),
        threshold=0.7,
    )


async def actual_output(tc, golden: dict) -> str:
    """The text the golden judges: the opening line for `turn: greeting`, else the reply."""
    if golden.get("turn") == "greeting":
        return (await run_conversation(tc, [])).greeting
    conversation = await run_conversation(tc, [golden["input"]])
    return text_of(conversation.results[0])


async def build_cases(tenant_id: str, project_id: str) -> list[LLMTestCase]:
    """Run every golden of the project once and wrap the replies as test cases."""
    goldens_path = pathlib.Path("tenants") / tenant_id / "projects" / project_id / "evals"
    goldens = json.loads((goldens_path / "goldens.json").read_text())
    cases: list[LLMTestCase] = []
    for golden in goldens:
        tc = fake_context(tenant_id, project_id)
        cases.append(
            LLMTestCase(
                input=golden["input"],
                actual_output=await actual_output(tc, golden),
                context=[f"Expected behaviour: {golden['expected_behaviour']}"],
            )
        )
    return cases


def main(argv: list[str]) -> None:
    """CLI: tenant and project ids; writes tmp/reports/deepeval/<name>_<timestamp>.html."""
    load_dotenv(".env")
    tenant_id, project_id = argv[1], argv[2]
    cases = asyncio.run(build_cases(tenant_id, project_id))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    evaluate(
        test_cases=cases,
        metrics=[reception_line_metric()],
        display_config=DisplayConfig(file_type="html", file_output_dir=str(REPORT_DIR)),
        identifier=f"{tenant_id}-{project_id}",
    )


if __name__ == "__main__":
    main(sys.argv)
