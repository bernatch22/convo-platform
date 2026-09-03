"""Produce the DeepEval HTML report for a project's goldens — on one model, or on several.

Decisions: docs/decisions/convo.testing.reports.report.md
"""

import argparse
import asyncio
import json
import os
import pathlib
import sys
from datetime import datetime
from types import ModuleType
from typing import Any

from deepeval import evaluate
from deepeval.evaluate.configs import DisplayConfig
from deepeval.test_case import ConversationalTestCase, LLMTestCase
from dotenv import load_dotenv

from convo.evals.filing import file_run, metrics_from
from convo.providers import llm
from convo.testing.harness import Conversation, fake_context, run_conversation
from convo.testing.metrics.deepeval import (
    conversational_test_case_for,
    inputs_for,
    project_metrics,
    test_case_for,
    tool_descriptions,
)
from convo.testing.reports import matrix

REPORT_DIR = pathlib.Path("tmp/reports/deepeval")  # generated artifact, not versioned
DEFAULT_SUITE = "report"  # what this CLI files under when nobody names a suite

# Ring 1 is scored on TEXT, and a .env with the voice keys in it makes
# `build_session` open a Soniox socket per golden that has no job context to
# borrow an http session from — minutes of retries and stack traces around the
# same replies. `tests/conftest.py` strips the same three keys for the same
# reason; this is that fixture, for the CLI.
VOICE_KEYS = ("SONIOX_API_KEY", "ELEVENLABS_API_KEY", "ELEVEN_API_KEY")

# The suite name a run is filed under. It carries the model because the whole
# point of the exercise is two runs of one suite that must not be confused.
SUITE = "ring1"


def suite_name(tenant_id: str, project_id: str, model: str, shape: str) -> str:
    """`ring1@<model>_<tenant>-<project>-<shape>` — what the run is filed and named after."""
    return f"{SUITE}@{model}_{tenant_id}-{project_id}-{shape}"


async def build_runs(
    tenant_id: str, project_id: str, model: str | None
) -> list[tuple[dict[str, Any], Conversation, dict[str, str]]]:
    """Run every golden of the project once on `model` and keep what both case shapes need."""
    goldens = json.loads((_evals_dir(tenant_id, project_id) / "goldens.json").read_text())
    runs = []
    for golden in goldens:
        tc = fake_context(tenant_id, project_id, llm_model=model)
        conversation = await run_conversation(tc, inputs_for(golden))
        runs.append((golden, conversation, tool_descriptions(tc)))
    return runs


def turn_cases(runs: list[tuple[dict[str, Any], Conversation, dict[str, str]]]) -> list:
    """One `LLMTestCase` per golden: the judged turn, what it called, what was expected."""
    return [
        test_case_for(golden, conversation, described) for golden, conversation, described in runs
    ]


def call_cases(runs: list[tuple[dict[str, Any], Conversation, dict[str, str]]]) -> list:
    """One `ConversationalTestCase` per golden: the whole call, greeting and platform writes."""
    return [
        conversational_test_case_for(
            conversation,
            described,
            scenario=golden["expected_behaviour"],
            name=golden["input"],
        )
        for golden, conversation, described in runs
    ]


def turn_metrics(metrics: ModuleType) -> list:
    """The project's turn-level metrics: how the reply reads, and what it called."""
    return [metrics.line_metric(), metrics.tool_correctness()]


def call_metrics(metrics: ModuleType) -> list:
    """The project's whole-call metrics: both deterministic, so free unless something is wrong."""
    return [metrics.grounded_facts_dag(), metrics.keeps_the_register()]


async def score(tenant_id: str, project_id: str, model: str) -> list[matrix.Score]:
    """Run the goldens on one model, write its HTML, and return every verdict it earned."""
    metrics = project_metrics(tenant_id, project_id)
    runs = await build_runs(tenant_id, project_id, model)
    turns = _evaluate(turn_cases(runs), turn_metrics(metrics), tenant_id, project_id, model, "turn")
    calls = _evaluate(call_cases(runs), call_metrics(metrics), tenant_id, project_id, model, "call")
    return [*matrix.read(turns), *matrix.read(calls)]


def write_matrix(built: matrix.Matrix, tenant_id: str, project_id: str) -> pathlib.Path:
    """Write the metric × model table next to the HTML and answer with its path."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"matrix_{tenant_id}-{project_id}_{stamp}.md"
    path.write_text(matrix.markdown(built, title=f"{tenant_id}/{project_id} — ring 1") + "\n")
    return path


def main(argv: list[str]) -> None:
    """CLI: tenant, project and the models to measure; HTML each, one table at the end."""
    load_dotenv(".env")
    text_only()
    args = _parse(argv[1:])
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    runs = {model: asyncio.run(score(args.tenant, args.project, model)) for model in args.model}
    built = matrix.build(runs)
    table = matrix.markdown(built, title=f"{args.tenant}/{args.project} — ring 1")
    print("\n" + table)
    print(f"\nwritten: {write_matrix(built, args.tenant, args.project)}")


def text_only() -> None:
    """Drop the voice keys from this process: ring 1 reads transcripts, never audio."""
    for key in VOICE_KEYS:
        os.environ.pop(key, None)


def _parse(args: list[str]) -> argparse.Namespace:
    """tenant, project, and `--model` once per model — default: the platform's own."""
    parser = argparse.ArgumentParser(prog="convo evals report", description=__doc__)
    parser.add_argument("tenant")
    parser.add_argument("project")
    parser.add_argument(
        "--model",
        action="append",
        choices=list(llm.ALLOWED_MODELS),
        help="measure this model; repeat it to compare (default: the platform's own)",
    )
    parsed = parser.parse_args(args)
    parsed.model = parsed.model or [llm.DEFAULT_MODEL]
    return parsed


def _evaluate(
    cases: list[LLMTestCase] | list[ConversationalTestCase],
    metrics: list,
    tenant_id: str,
    project_id: str,
    model: str,
    shape: str,
) -> Any:
    """One run over one case shape, filed with the control plane, HTML under the model's name."""
    result = evaluate(
        test_cases=cases,
        metrics=metrics,
        display_config=DisplayConfig(
            file_type="html",
            file_output_dir=str(REPORT_DIR),
            inspect_after_run=False,
        ),
        identifier=suite_name(tenant_id, project_id, model, shape),
    )
    file_run(
        tenant_id,
        project_id,
        suite_name(tenant_id, project_id, model, shape),
        metrics_from(result.test_results),
        report_html=_newest_html(),
    )
    return result


def _newest_html() -> str | None:
    """The HTML this run just wrote, so the console links the evidence instead of naming it."""
    written = sorted(REPORT_DIR.glob("*.html"), key=lambda path: path.stat().st_mtime)
    return str(written[-1]) if written else None


def _evals_dir(tenant_id: str, project_id: str) -> pathlib.Path:
    """Where a project keeps its goldens and its metrics."""
    return pathlib.Path("tenants") / tenant_id / "projects" / project_id / "evals"


if __name__ == "__main__":
    main(sys.argv)
