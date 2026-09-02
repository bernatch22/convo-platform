"""What a night leaves behind: one page, one line of history, one row on the console.

Decisions: docs/decisions/convo.testing.reports.nightly_report.md
"""

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from convo.testing.reports.nightly_html import page

SUITE_ID = "ring2"  # what the console files a nightly under
FILING_TIMEOUT_S = 10.0
COLUMNS = (
    "date",
    "suite",
    "status",
    "passed",
    "failed",
    "worst_metric",
    "worst_score",
    "seconds",
    "judge_usd",
    "report",
)


def worst(metrics: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The one metric a reader should look at first: the lowest of the failing ones."""
    if not metrics:
        return None
    failing = [row for row in metrics if row["failed"]]
    return min(failing or metrics, key=lambda row: row["score"])


def write_page(
    out: Path, date: str, views: list[dict[str, Any]], skipped: list[dict[str, Any]], **facts
) -> Path:
    """Render the night as one self-contained HTML file and answer with where it went."""
    report = out / "index.html"
    report.write_text(page(date=date, suites=views, skipped=skipped, **facts), encoding="utf-8")
    return report


def index_row(date: str, view: dict[str, Any], report: Path) -> list[str]:
    """One night of one suite as the tab-separated line appended to the history."""
    low = view["worst"]
    return [
        date,
        view["id"],
        view["status"],
        str(view["passed"]),
        str(view["failed"]),
        low["metric"] if low else "-",
        f"{low['score']:.3f}" if low else "-",
        f"{view['seconds']:.0f}",
        f"{view['judge_usd']:.4f}",
        str(report),
    ]


def append_index(path: Path, rows: list[list[str]]) -> None:
    """Append tonight's lines to the history, writing the header the first time only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8") as history:
        if new:
            history.write("\t".join(COLUMNS) + "\n")
        for row in rows:
            history.write("\t".join(row) + "\n")


def file_run(console: str, view: dict[str, Any], report: Path, git_sha: str) -> bool:
    """Register one suite's night with the control plane; True when the console stored it."""
    tenant, project = view["id"].split("/", 1)
    body = {
        "tenant": tenant,
        "project": project,
        "suite": SUITE_ID,
        "status": view["status"],
        "metrics": view["metrics"],
        "git_sha": git_sha,
        "report_html": str(report),
        "milestone": None,
    }
    request = urllib.request.Request(
        f"{console.rstrip('/')}/evals/runs",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=FILING_TIMEOUT_S):  # noqa: S310 — ours
            return True
    except (urllib.error.URLError, OSError):
        return False
