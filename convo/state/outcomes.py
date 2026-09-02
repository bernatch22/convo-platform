"""Outcomes: what the platform DID to the business, read straight off the append-only log.

Decisions: docs/decisions/convo.state.outcomes.md
"""

import time
from datetime import date, datetime, timedelta
from datetime import time as clock
from typing import Any

from convo.state.events import Event
from convo.state.store import SessionRow, Store

IRREVERSIBLE = "irreversible"
CALL = "tool.call"
GRANTED = "confirm.granted"
RESULT = "tool.result"
ERROR = "tool.error"

DEFAULT_DAYS = 14
MAX_DAYS = 90
DEFAULT_ROWS = 50
MAX_ROWS = 500

# How far before the window a session may have STARTED and still hold a transaction
# inside it. An event's clock is its session's start plus `t_ms`, so a call that began
# at 23:58 writes into the next day; a day of slack covers every call a human makes.
SLACK_S = 86400.0

DONE = "done"
FAILED = "failed"
PENDING = "pending"


def outcomes(
    store: Store,
    tenant: str | None = None,
    project: str | None = None,
    days: int = DEFAULT_DAYS,
    limit: int = DEFAULT_ROWS,
    now: float | None = None,
) -> dict[str, Any]:
    """Every irreversible transaction in the window: totals, counts by verb by day, recent rows."""
    now = time.time() if now is None else now
    days = max(1, min(days, MAX_DAYS))
    limit = max(1, min(limit, MAX_ROWS))
    axis = _axis(now, days)
    since = datetime.combine(axis[0], clock.min).timestamp()

    rows = _transactions(store, tenant, project, since)
    return {
        "tenant": tenant,
        "project": project,
        "days": days,
        "since": since,
        "until": now,
        "totals": _totals(rows),
        "verbs": _by_verb(rows),
        "series": _by_day(rows, axis),
        "rows": rows[:limit],
    }


def _transactions(
    store: Store, tenant: str | None, project: str | None, since: float
) -> list[dict[str, Any]]:
    """Every transaction of every matching session, newest first, already inside the window."""
    rows: list[dict[str, Any]] = []
    for session in store.sessions():
        if not _matches(session, tenant, project) or session.started_at < since - SLACK_S:
            continue
        found = _of_session(session, store.events(session.id))
        rows.extend(row for row in found if row["at"] >= since)
    rows.sort(key=lambda row: (row["at"], row["seq"]), reverse=True)
    return rows


def _of_session(session: SessionRow, events: list[Event]) -> list[dict[str, Any]]:
    """One session's transactions: the irreversible calls, each with its yes and its outcome."""
    granted: dict[str, int] = {}
    waiting: dict[str, list[int]] = {}
    rows: list[dict[str, Any]] = []

    for event in events:
        tool = str(event.payload.get("tool") or "?")
        if event.kind == GRANTED:
            granted[tool] = granted.get(tool, 0) + 1
        elif event.kind == CALL and event.payload.get("side_effect") == IRREVERSIBLE:
            confirmed = granted.get(tool, 0) > 0
            granted[tool] = granted.get(tool, 0) - 1 if confirmed else 0
            rows.append(_row(session, event, tool, confirmed))
            waiting.setdefault(tool, []).append(len(rows) - 1)
        elif event.kind in (RESULT, ERROR):
            _close(rows, waiting.get(tool) or [], event)

    return rows


def _row(session: SessionRow, event: Event, tool: str, confirmed: bool) -> dict[str, Any]:
    """One transaction as the console reads it, before its result has landed."""
    at = session.started_at + event.t_ms / 1000
    return {
        "session": session.id,
        "tenant": session.tenant,
        "project": session.project,
        "channel": session.channel,
        "seq": event.seq,
        "at": at,
        "day": _day(at),
        "verb": tool,
        "confirmed": confirmed,
        "status": PENDING,
        "summary": None,
    }


def _close(rows: list[dict[str, Any]], waiting: list[int], event: Event) -> None:
    """Give the oldest unanswered call of that name its outcome and the log's own summary."""
    if not waiting:
        return  # a result for a read or a write, or a log that starts mid-call
    row = rows[waiting.pop(0)]
    row["status"] = DONE if event.kind == RESULT else FAILED
    row["summary"] = str(event.payload.get("summary") or "").strip() or None


def _totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    """The four numbers across the top: how many ran, said yes, broke, and in how many calls."""
    return {
        "transactions": len(rows),
        "confirmed": sum(1 for row in rows if row["confirmed"]),
        "failed": sum(1 for row in rows if row["status"] == FAILED),
        "sessions": len({row["session"] for row in rows}),
    }


def _by_verb(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One counter per verb, busiest first — the board's headline, whatever the verbs are called."""
    counts: dict[str, dict[str, Any]] = {}
    for row in rows:
        blank = {"verb": row["verb"], "count": 0, "confirmed": 0, "failed": 0, "pending": 0}
        tally = counts.setdefault(row["verb"], blank)
        tally["count"] += 1
        tally["confirmed"] += int(row["confirmed"])
        tally["failed"] += int(row["status"] == FAILED)
        tally["pending"] += int(row["status"] == PENDING)
    return sorted(counts.values(), key=lambda tally: (-tally["count"], tally["verb"]))


def _by_day(rows: list[dict[str, Any]], axis: list[date]) -> list[dict[str, Any]]:
    """The bars: every day of the window, empty ones included, so the strip has a stable axis."""
    series = {day.isoformat(): {"day": day.isoformat(), "total": 0, "verbs": {}} for day in axis}
    for row in rows:
        bucket = series.get(row["day"])
        if bucket is None:
            continue  # a transaction from a session that ran past midnight into tomorrow
        bucket["total"] += 1
        bucket["verbs"][row["verb"]] = bucket["verbs"].get(row["verb"], 0) + 1
    return list(series.values())


def _axis(now: float, days: int) -> list[date]:
    """The window's days, oldest first, in the box's own timezone — an operator's day, not UTC."""
    today = datetime.fromtimestamp(now).date()
    return [today - timedelta(days=offset) for offset in reversed(range(days))]


def _day(at: float) -> str:
    return datetime.fromtimestamp(at).date().isoformat()


def _matches(session: SessionRow, tenant: str | None, project: str | None) -> bool:
    return (tenant is None or session.tenant == tenant) and (
        project is None or session.project == project
    )
