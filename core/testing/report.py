"""Produce the DeepEval HTML report for a project's goldens.

`deepeval test run` is the CI gate (pass/fail); this module is the reviewer's
view: it runs the same goldens through the same cases and the same metrics and
writes a self-contained HTML under tmp/reports/deepeval/. Usage:

    uv run python -m core.testing.report clinica-norte reagendamiento

The metrics are the project's own (`evals/metrics.py`), never a copy kept here:
a criterion that drifts between the gate and the report is worse than no report,
because it shows a reviewer a score CI never computed. ArgumentCorrectness is
the one metric the suite runs and this does not — `evaluate()` scores every case
with every metric, and a judge asked about the arguments of a turn that called
nothing has nothing to read. It stays in the pytest suite, where it is applied
only to the goldens that call.
"""

import asyncio
import json
import pathlib
import sys

from deepeval import evaluate
from deepeval.evaluate.configs import DisplayConfig
from deepeval.test_case import LLMTestCase
from dotenv import load_dotenv

from core.testing.deepeval import (
    inputs_for,
    project_metrics,
    test_case_for,
    tool_descriptions,
)
from core.testing.harness import fake_context, run_conversation

REPORT_DIR = pathlib.Path("tmp/reports/deepeval")  # generated artifact, not versioned


async def build_cases(tenant_id: str, project_id: str) -> list[LLMTestCase]:
    """Run every golden of the project once and wrap each run as a test case."""
    goldens_path = pathlib.Path("tenants") / tenant_id / "projects" / project_id / "evals"
    goldens = json.loads((goldens_path / "goldens.json").read_text())
    cases: list[LLMTestCase] = []
    for golden in goldens:
        tc = fake_context(tenant_id, project_id)
        conversation = await run_conversation(tc, inputs_for(golden))
        cases.append(test_case_for(golden, conversation, tool_descriptions(tc)))
    return cases


def main(argv: list[str]) -> None:
    """CLI: tenant and project ids; writes tmp/reports/deepeval/<name>_<timestamp>.html."""
    load_dotenv(".env")
    tenant_id, project_id = argv[1], argv[2]
    metrics = project_metrics(tenant_id, project_id)
    cases = asyncio.run(build_cases(tenant_id, project_id))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    evaluate(
        test_cases=cases,
        metrics=[metrics.reception_line(), metrics.tool_correctness()],
        display_config=DisplayConfig(file_type="html", file_output_dir=str(REPORT_DIR)),
        identifier=f"{tenant_id}-{project_id}",
    )


if __name__ == "__main__":
    main(sys.argv)
