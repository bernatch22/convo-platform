"""The business view: the reservations themselves, read off the customer's own system.

Decisions: docs/decisions/convo.domain.business.md
"""

from typing import Any

from convo.adapters.base import LIST_RECORDS, PLAIN
from convo.domain.context import Tenant
from convo.state import outcomes as core_outcomes
from convo.state.store import Store

DEFAULT_DAYS = core_outcomes.DEFAULT_DAYS
MAX_DAYS = core_outcomes.MAX_DAYS
DEFAULT_ROWS = 200
MAX_ROWS = 1000

ROW_KEYS = ("id", "who", "contact", "when", "handled_by", "state", "tone", "detail", "at")

# What a project whose systems offer no record view answers with. The console reads
# `shape: null` as "there is no such view here" and says so in words, which is the one
# honest thing to draw instead of an empty agenda nobody ever had.
EMPTY: dict[str, Any] = {"shape": None, "labels": {}, "rows": [], "systems": []}


async def records(
    tenant: Tenant,
    project_id: str,
    store: Store,
    days: int = DEFAULT_DAYS,
    limit: int = DEFAULT_ROWS,
    now: float | None = None,
) -> dict[str, Any]:
    """One project's business records, per system, each carrying the call that last touched it."""
    days = max(1, min(days, MAX_DAYS))
    limit = max(1, min(limit, MAX_ROWS))
    transactions = _by_id(store, tenant.id, project_id, days, now)
    views = [
        {**view, "rows": _ordered(_joined(view["rows"], transactions))[:limit]}
        for view in await _ask(tenant)
    ]
    first = views[0] if views else EMPTY

    return {
        "tenant": tenant.id,
        "project": project_id,
        "days": days,
        "shape": first["shape"],
        "labels": first["labels"],
        "systems": first["systems"],
        "rows": first["rows"],
        "views": views,
    }


async def _ask(tenant: Tenant) -> list[dict[str, Any]]:
    """Every system of this tenant that has a view to offer, in the tenant's own order."""
    views = []
    for name, adapter in tenant.build_adapters().items():
        if not adapter.supports(LIST_RECORDS):
            continue
        answer = await adapter.execute(LIST_RECORDS, {})
        if not isinstance(answer, dict):
            continue
        views.append(
            {
                "shape": answer.get("shape"),
                "labels": dict(answer.get("labels") or {}),
                "rows": [_clean(row) for row in answer.get("rows") or []],
                "systems": [name],
            }
        )
    return views


def _clean(row: Any) -> dict[str, Any]:
    """One row of the adapter's answer, reduced to the keys the console reads and nothing else."""
    given = row if isinstance(row, dict) else {}
    kept = {key: given.get(key) for key in ROW_KEYS}
    kept["id"] = str(kept["id"] or "")
    kept["who"] = str(kept["who"] or "")
    kept["state"] = str(kept["state"] or "")
    kept["tone"] = str(kept["tone"] or PLAIN)
    return kept


def _by_id(
    store: Store, tenant: str, project: str, days: int, now: float | None
) -> dict[str, dict[str, Any]]:
    """The newest transaction in the window that named each business id, keyed by that id."""
    board = core_outcomes.outcomes(
        store, tenant=tenant, project=project, days=days, limit=core_outcomes.MAX_ROWS, now=now
    )
    newest: dict[str, dict[str, Any]] = {}
    for row in board["rows"]:
        identifier = _identifier_in(row.get("summary"))
        if identifier:
            newest.setdefault(identifier, row)
    return newest


def _identifier_in(summary: str | None) -> str:
    """The one token of a log summary that could be a business id: never a word, never a name."""
    for word in str(summary or "").split():
        token = word.strip(".,;:()").strip()
        if len(token) > 3 and any(c.isdigit() for c in token) and "-" in token:
            return token
    return ""


def _joined(
    rows: list[dict[str, Any]], transactions: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Give each business record the call that last touched it, or a dash where none did."""
    joined = []
    for row in rows:
        found = transactions.get(row["id"])
        joined.append(
            {
                **row,
                "at": row["at"] if row["at"] is not None else (found or {}).get("at"),
                "session": (found or {}).get("session"),
                "verb": (found or {}).get("verb"),
                "confirmed": bool((found or {}).get("confirmed")),
                "channel": (found or {}).get("channel"),
            }
        )
    return joined


def _ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What a call touched first, newest change on top; then the rest of the book by its date."""
    touched = sorted(
        (row for row in rows if row["at"] is not None),
        key=lambda row: row["at"],
        reverse=True,
    )
    untouched = sorted(
        (row for row in rows if row["at"] is None), key=lambda row: str(row["when"] or "")
    )
    return touched + untouched
