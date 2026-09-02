"""Ring 2 as a habit: every night the box phones its own fleet and writes down what it heard.

Decisions: docs/decisions/convo.testing.reports.nightly.md
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from convo.session.router import git_sha
from convo.testing.reports import nightly_report as report

SUITE_FILE = "test_ring2.py"  # the convention by which a project declares it has a ring 2
GOLDENS_FILE = "ring2_goldens.json"

BUDGET = 8  # live conversations one night may spend, across the whole fleet
DEADLINE_S = 20 * 60  # the whole night, not one suite
OUT = Path("tmp/evals")
INDEX = OUT / "index.tsv"

DONE, FAILED = "done", "failed"
API_ENV = "CONVO_API"
DEFAULT_API = "http://127.0.0.1:8090"
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Suite:
    """One project's ring 2: where pytest is pointed, and how many live calls that costs."""

    tenant: str
    project: str
    target: Path
    calls: int

    @property
    def id(self) -> str:
        """`tenant/project` — how a suite is named in the log, the index and `--only`."""
        return f"{self.tenant}/{self.project}"


@dataclass
class Result:
    """A suite after the night ran it: its verdict, its scores, and the calls behind them."""

    suite: Suite
    status: str
    seconds: float = 0.0
    metrics: list[dict[str, Any]] = field(default_factory=list)
    cases: list[dict[str, Any]] = field(default_factory=list)
    judge_usd: float = 0.0
    detail: str | None = None

    @property
    def passed(self) -> int:
        """How many metric verdicts cleared their threshold across every case."""
        return sum(int(row["passed"]) for row in self.metrics)

    @property
    def failed(self) -> int:
        """How many did not — the number that decides the colour of the night."""
        return sum(int(row["failed"]) for row in self.metrics)

    def view(self) -> dict[str, Any]:
        """This result as the plain data the report writes down; the page computes nothing."""
        return {
            "id": self.suite.id,
            "status": self.status,
            "calls": self.suite.calls,
            "seconds": self.seconds,
            "judge_usd": self.judge_usd,
            "detail": self.detail,
            "passed": self.passed,
            "failed": self.failed,
            "worst": report.worst(self.metrics),
            "metrics": self.metrics,
            "cases": self.cases,
        }


def discover(root: Path = REPO_ROOT, only: list[str] | None = None) -> list[Suite]:
    """Every ring-2 suite the fleet declares, with the number of live calls each one makes."""
    suites: list[Suite] = []
    for target in sorted(root.glob(f"tenants/*/projects/*/evals/{SUITE_FILE}")):
        suite = Suite(
            tenant=target.parents[3].name,
            project=target.parents[1].name,
            target=target.relative_to(root),
            calls=_calls_in(target.parent / GOLDENS_FILE),
        )
        if only is None or suite.id in only:
            suites.append(suite)
    return suites


def affordable(suites: list[Suite], budget: int = BUDGET) -> tuple[list[Suite], list[Suite]]:
    """Split the fleet into what tonight can pay for and what it cannot, whole suites only."""
    taken: list[Suite] = []
    skipped: list[Suite] = []
    spent = 0
    for suite in suites:
        if spent + suite.calls <= budget:
            taken.append(suite)
            spent += suite.calls
        else:
            skipped.append(suite)
    return taken, skipped


def run_suite(suite: Suite, out: Path, log, deadline_s: float, api: str) -> Result:
    """Run one project's ring 2 as a child process, killed at the deadline, scores read back."""
    results = out / f"{suite.tenant}-{suite.project}"
    results.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    log.flush()
    child = subprocess.Popen(  # noqa: S603 — our own binary, our own paths
        _command(suite.target),
        cwd=REPO_ROOT,
        env=_child_env(results, api),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        code = child.wait(timeout=deadline_s)
    except subprocess.TimeoutExpired:
        _kill(child)
        code = None
    metrics, cases, judge_usd = scored(results)
    status, detail = status_of(code, metrics, deadline_s)
    return Result(
        suite=suite,
        status=status,
        seconds=round(time.monotonic() - started, 1),
        metrics=metrics,
        cases=cases,
        judge_usd=judge_usd,
        detail=detail,
    )


def status_of(
    code: int | None, metrics: list[dict[str, Any]], deadline_s: float = DEADLINE_S
) -> tuple[str, str | None]:
    """A suite's verdict from its exit code AND its scores — a metric that failed is red."""
    failed = sum(int(row["failed"]) for row in metrics)
    if code is None:
        return FAILED, f"killed after {deadline_s:.0f}s"
    if code != 0:
        return FAILED, f"the suite exited {code} — read the log"
    if failed:
        return FAILED, f"{failed} metric verdict(s) failed; pytest passed them as flaky"
    return DONE, None


def scored(results: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    """DeepEval's own JSON, read back as metric rows, conversational cases and the judge's bill."""
    written = sorted(results.glob("test_run_*.json")) if results.is_dir() else []
    if not written:
        return [], [], 0.0
    try:
        data = json.loads(written[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], [], 0.0
    metrics = [_metric_row(row) for row in data.get("metricsScores", []) if row.get("metric")]
    cases = list(data.get("conversationalTestCases") or []) + list(data.get("testCases") or [])
    return metrics, cases, float(data.get("evaluationCost") or 0.0)


def main(argv: list[str]) -> int:
    """CLI: run every ring-2 suite the budget allows and leave the log, the page and the line."""
    args = _parser().parse_args(argv[1:])
    load_dotenv(REPO_ROOT / ".env")
    console = args.console or args.api
    date = args.date or time.strftime("%Y-%m-%d")
    out = REPO_ROOT / OUT / date
    out.mkdir(parents=True, exist_ok=True)
    taken, skipped = affordable(discover(only=args.only or None), args.budget)
    if args.dry_run:
        return _quote(taken, skipped, args.budget)

    with (REPO_ROOT / OUT / f"{date}.log").open("a", encoding="utf-8") as log:
        say = _sayer(log)
        say(f"── ring 2, {date} · {git_sha()} · api {args.api} · budget {args.budget} calls")
        for suite in skipped:
            say(f"   SKIPPED {suite.id}: {suite.calls} calls do not fit tonight's budget")
        results: list[Result] = []
        deadline = time.monotonic() + args.deadline
        for suite in taken:
            say(f"   {suite.id}: {suite.calls} calls · {suite.target}")
            left = max(1.0, deadline - time.monotonic())
            results.append(run_suite(suite, out, log, left, args.api))
            say(f"   {suite.id}: {results[-1].status} in {results[-1].seconds:.0f}s")
        page = _write(out, date, results, skipped, args.budget)
        for run in results:
            filed = report.file_run(console, run.view(), page, git_sha())
            say(f"   {run.suite.id}: {'filed with' if filed else 'NOT filed —'} {console}")
        return _verdict(say, results, skipped, page)


def _calls_in(goldens: Path) -> int:
    """How many live calls a project's ring-2 goldens file describes; 0 when it has none."""
    try:
        return len(json.loads(goldens.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        return 0


def _command(target: Path) -> list[str]:
    """`deepeval test run <target>`, from the virtualenv that is running this process."""
    binary = Path(sys.executable).parent / "deepeval"
    runner = str(binary) if binary.exists() else "deepeval"
    return [runner, "test", "run", str(target), "--color", "no"]


def _child_env(results: Path, api: str) -> dict[str, str]:
    """This process's environment plus where the suite calls and where it drops its scores."""
    env = dict(os.environ)
    env[API_ENV] = api
    env["DEEPEVAL_RESULTS_FOLDER"] = str(results)
    env["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
    return env


def _metric_row(row: dict[str, Any]) -> dict[str, Any]:
    """One of DeepEval's `metricsScores` as the row `POST /evals/runs` stores."""
    scores = [value for value in row.get("scores", []) if isinstance(value, (int, float))]
    return {
        "metric": str(row["metric"]),
        "score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "passed": int(row.get("passes", 0)),
        "failed": int(row.get("fails", 0)) + int(row.get("errors", 0)),
    }


def _write(out: Path, date: str, results: list[Result], skipped: list[Suite], budget: int) -> Path:
    """Write the page and the index line, and answer with the page's path from the repo root."""
    views = [run.view() for run in results]
    page = report.write_page(
        out,
        date,
        views,
        [{"id": suite.id, "calls": suite.calls} for suite in skipped],
        git=git_sha(),
        budget=budget,
        spent=sum(run.suite.calls for run in results),
    ).relative_to(REPO_ROOT)
    report.append_index(REPO_ROOT / INDEX, [report.index_row(date, view, page) for view in views])
    return page


def _sayer(log):
    """A narrator that writes to the journal and to the night's log, in that one order."""

    def say(line: str) -> None:
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    return say


def _quote(taken: list[Suite], skipped: list[Suite], budget: int) -> int:
    """`--dry-run`: what tonight would call and what it would refuse to, spending nothing."""
    for suite in taken:
        print(f"   would call {suite.id}: {suite.calls} conversations")
    for suite in skipped:
        print(f"   would SKIP {suite.id}: {suite.calls} conversations do not fit")
    print(f"   {sum(suite.calls for suite in taken)}/{budget} of the budget")
    return 1 if skipped else 0


def _verdict(say, results: list[Result], skipped: list[Suite], page: Path) -> int:
    """Say how the night went and answer with the exit code that makes red mean red."""
    red = [run for run in results if run.status != DONE]
    say(f"── report {page} · index {INDEX}")
    for run in red:
        say(f"   RED {run.suite.id}: {run.detail or 'a metric did not clear its threshold'}")
    if skipped:
        say(f"   RED {len(skipped)} suite(s) skipped: raise --budget deliberately, or drop them")
    if not results:
        say("   RED nothing ran: no ring-2 suite fitted the budget")
        return 1
    return 1 if (red or skipped) else 0


def _kill(child: subprocess.Popen) -> None:
    """Kill a child that ran past the deadline and reap it, so no zombie holds a provider open."""
    child.kill()
    try:
        child.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def _parser() -> argparse.ArgumentParser:
    """The night's knobs: where to call, what to spend, how long to wait, what to run."""
    parser = argparse.ArgumentParser(prog="python -m core.testing.nightly")
    parser.add_argument("--api", default=os.getenv(API_ENV, DEFAULT_API))
    parser.add_argument("--console", default=None, help="where to file the run (default: --api)")
    parser.add_argument("--budget", type=int, default=BUDGET, help="live calls tonight may spend")
    parser.add_argument("--deadline", type=float, default=DEADLINE_S, help="seconds, whole run")
    parser.add_argument("--date", default=None, help="name the night (default: today)")
    parser.add_argument("--only", action="append", default=[], help="tenant/project, repeatable")
    parser.add_argument("--dry-run", action="store_true", help="price the night, call nobody")
    return parser


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
