"""Self-registration: a run that finished anywhere tells the control plane it happened.

The box can launch a run itself, but most runs are still started by a person or
by CI (`deepeval test run`, `python -m core.testing.report`). Those are the runs
worth comparing against, so they file themselves here instead of living only in
somebody's terminal scrollback.

A control plane that is not answering is not an error: the local run still
produced its HTML and its exit code. `file_run` says whether the board heard
it and never raises — an eval must not fail because a console was down.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from convo.session.router import git_sha

log = logging.getLogger("platform.evals")

API_ENV = "CONVO_API"
DEFAULT_API = "http://127.0.0.1:8090"
TIMEOUT_S = 5.0


def file_run(
    tenant: str,
    project: str,
    suite: str,
    metrics: list[dict[str, Any]],
    status: str = "done",
    report_html: str | None = None,
    milestone: str | None = None,
) -> bool:
    """POST one finished run to `POST /evals/runs`; True when the control plane stored it."""
    body = {
        "tenant": tenant,
        "project": project,
        "suite": suite,
        "status": status,
        "metrics": metrics,
        "git_sha": git_sha(),
        "report_html": report_html,
        "milestone": milestone,
    }
    request = urllib.request.Request(
        f"{control_plane_url()}/evals/runs",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S):  # noqa: S310 — our own control plane
            return True
    except (urllib.error.URLError, OSError) as error:
        log.info("eval run not filed (%s); the report on disk is still the evidence", error)
        return False


def metrics_from(test_results: list[Any]) -> list[dict[str, Any]]:
    """DeepEval's `EvaluationResult.test_results` folded into one row per metric.

    Every case is scored by every metric, so the run's number for a metric is
    the mean over its cases and its tally is how many of them cleared the
    threshold — the same aggregation `deepeval test run` prints at the end.
    """
    scores: dict[str, list[float]] = {}
    passes: dict[str, int] = {}
    fails: dict[str, int] = {}
    for result in test_results:
        for metric in getattr(result, "metrics_data", None) or []:
            name = metric.name
            scores.setdefault(name, []).append(float(metric.score or 0.0))
            tally = passes if metric.success else fails
            tally[name] = tally.get(name, 0) + 1
    return [
        {
            "metric": name,
            "score": round(sum(values) / len(values), 4) if values else 0.0,
            "passed": passes.get(name, 0),
            "failed": fails.get(name, 0),
        }
        for name, values in sorted(scores.items())
    ]


def control_plane_url() -> str:
    """Where `api.py` answers — `CONVO_API`, or the port the README tells you to run it on."""
    return os.getenv(API_ENV, DEFAULT_API).rstrip("/")
