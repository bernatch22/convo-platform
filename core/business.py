"""The business view: the reservations themselves, read off the customer's own system.

`core/outcomes.py` answers *what did the platform do* — irreversible calls
counted off the append-only log, whose summaries were PII-filtered on the way
in and stay that way. That is the transactional reading, and it is the right
one for an auditor. It is the wrong one for the person running the contact
centre, who asked a much plainer question: **who is coming, when, with whom,
and is that booking still standing.**

That question is not answerable from the log, and deliberately so. The log
holds `appointment ap-20260904-1000-trau now 2026-09-04T10:00` because the
name was masked before it was written — the platform is not the place a
patient's name is stored. The reservation, name and all, lives where it has
always lived: in the BUSINESS system. So this module goes and asks it.

**The route.** `api.py` → `core.registry` → the tenant's own adapters. The
registry is the one door core is allowed to open onto `tenants/` (it imports
each in try/except, and `tests/test_core_isolation.py` keeps every other file
in core honest). From there it is one capability, `LIST_RECORDS`, declared by
EVERY adapter that has a view to offer — a shop keeps its orders in one system
and its incidents in another, and those are two tables and not a longer one.
Nothing here knows what a clinic books or a shop ships: each adapter answers
with its own shape, its own labels and its own state words, and a tenant whose
systems have none answers `shape: null`, which the console shows as an honest
empty rather than a fake agenda.

**The join, and what it is for.** Each row's STATE comes from the business
system, because the business system is the authority on its own records — a
rescheduling is one cancel plus one booking to the platform, but it is *one
moved appointment* to the clinic, and only the clinic's own book can say so.
What the business system cannot know is which CONVERSATION produced the change
and whether the caller's yes was on record. That is exactly what the log has,
so the two are joined here.

The key is the appointment id, and the reason it works is a happy consequence
of the PII rule: an identifier is not a person, so it survives the mask and
lands in the log's summary verbatim (`appointment ap-… now …`). A business row
is matched to the newest transaction whose summary mentions its id; the row
then carries the session it came from, the verb that ran, and whether a
`confirm.granted` stood unspent before it. A substring match on an opaque id
is loose in principle — this is documented so nobody mistakes it for a foreign
key — and it is exact in practice because ids are minted from the slot they
book. A row nothing in the window mentions simply has no call behind it: it
was already on the book before we ever rang, and it says so with a dash.

The window is the same `days` the Board's counters use, so what the strip
counts and what the table links to cannot come from two different periods.
"""

from typing import Any

from core import outcomes as core_outcomes
from core.adapters.base import LIST_RECORDS, PLAIN
from core.context import Tenant
from core.state.store import Store

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
    """Every system of this tenant that has a view to offer, in the tenant's own order.

    One system used to answer and the rest were never asked, which was right
    while a business had one kind of record. It stopped being right the moment
    a shop kept orders in one system and incidents in another: the second view
    is not a longer table, it is a DIFFERENT table — its own shape, its own
    column headings, its own words for a state — and merging the two would have
    meant core deciding which of the business's vocabularies wins. So the read
    returns them all and the console draws one table each.

    The flat `shape`/`labels`/`rows` of the answer stay the first view. Not
    politeness towards an old client: it is what the endpoint has always meant
    by "this project's records", the reason the tenant's factory order is
    documented as meaning something, and it keeps a one-system tenant's answer
    byte-for-byte what it was.

    Adapters are built the way a session builds them — the tenant's own factory
    — and thrown away when this read is over: a console read must not be able
    to leave anything behind in a customer's system.
    """
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
    """The newest transaction in the window that named each business id, keyed by that id.

    Rows arrive newest first, so the first mention of an id wins and the ones
    behind it are the history of a record the table shows one line of.
    """
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
    """The one token of a log summary that could be a business id: never a word, never a name.

    A summary is prose a tool's own renderer wrote, so this cannot parse it. It
    can do the one thing that is safe: an id is minted from a slot and always
    reads `ap-20260904-1000-trau` or `TS-10432`, so a token with a hyphen or a
    digit in it and no space is a candidate and everything else is language.
    """
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
    """What a call touched first, newest change on top; then the rest of the book by its date.

    Two orderings in one table because the operator reads it for two reasons.
    A booking that just happened is the thing they came to check, so it leads
    however far away the appointment itself is; everything the platform never
    touched is the standing book, and a book reads soonest-first.
    """
    touched = sorted(
        (row for row in rows if row["at"] is not None),
        key=lambda row: row["at"],
        reverse=True,
    )
    untouched = sorted(
        (row for row in rows if row["at"] is None), key=lambda row: str(row["when"] or "")
    )
    return touched + untouched
