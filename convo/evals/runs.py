"""The read side of the eval runs: the list the console draws, and the diff between two of them.

A score alone says nothing — 0.82 is good or bad depending on what the same
suite scored yesterday. So every run this module hands out carries, per metric,
the delta against the previous run of the SAME tenant, project and suite. That
is the whole reason the runs are stored at all: a number you can compare.

Plain dicts in, plain dicts out, a `Store` and nothing else — the same shape
`core.control_plane` keeps, so an HTTP handler, a test and a CLI read
identically.
"""

from typing import Any

from convo.state.store import EvalRun, MetricScore, Store

DEFAULT_LIMIT = 50
RUNNING = "running"
DONE = "done"
FAILED = "failed"


def listing(
    store: Store,
    tenant: str | None = None,
    project: str | None = None,
    suite: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Stored runs, newest first, each already diffed against its own predecessor."""
    everything = store.eval_runs()
    wanted = [run for run in everything if _matches(run, tenant, project, suite)][:limit]
    return [view(run, previous(everything, run)) for run in wanted]


def find(store: Store, run_id: str) -> dict[str, Any] | None:
    """One run by id, diffed the same way, or None when nothing was ever stored under it."""
    everything = store.eval_runs()
    run = next((row for row in everything if row.id == run_id), None)
    return None if run is None else view(run, previous(everything, run))


def previous(runs: list[EvalRun], run: EvalRun) -> EvalRun | None:
    """The scored run before this one of the same suite — what its numbers are compared against.

    "Before" is by `started_at`, not by list position: a run filed by CI lands
    out of order and would otherwise diff against a future.
    """
    earlier = [
        row
        for row in runs
        if row.id != run.id
        and (row.tenant, row.project, row.suite) == (run.tenant, run.project, run.suite)
        and row.started_at < run.started_at
        and row.metrics
    ]
    return max(earlier, key=lambda row: row.started_at, default=None)


def view(run: EvalRun, before: EvalRun | None = None) -> dict[str, Any]:
    """One run as the console reads it: identity, verdict, and a delta per metric."""
    was = {metric.metric: metric.score for metric in (before.metrics if before else ())}
    return {
        "id": run.id,
        "tenant": run.tenant,
        "project": run.project,
        "suite": run.suite,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "git_sha": run.git_sha,
        "milestone": run.milestone,
        "report_html": run.report_html,
        "log_path": run.log_path,
        "detail": run.detail,
        "metrics": [_metric_view(metric, was) for metric in run.metrics],
        "previous": before.id if before else None,
    }


def _metric_view(metric: MetricScore, was: dict[str, float]) -> dict[str, Any]:
    """One metric's line: its score, its cases, and what it gained or lost since last time."""
    before = was.get(metric.metric)
    return {
        "metric": metric.metric,
        "score": metric.score,
        "passed": metric.passed,
        "failed": metric.failed,
        "delta": None if before is None else round(metric.score - before, 4),
    }


def _matches(run: EvalRun, tenant: str | None, project: str | None, suite: str | None) -> bool:
    return (
        (tenant is None or run.tenant == tenant)
        and (project is None or run.project == project)
        and (suite is None or run.suite == suite)
    )
