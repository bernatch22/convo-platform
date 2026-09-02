"""What the platform did to the business: outcomes off the log, reservations off its systems."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from convo.api.deps import Reader
from convo.domain import business
from convo.session.registry import load_registry
from convo.state import outcomes as core_outcomes

router = APIRouter()


@router.get("/outcomes")
async def outcomes(
    store: Reader,
    tenant: str | None = None,
    project: str | None = None,
    days: Annotated[int, Query(ge=1, le=core_outcomes.MAX_DAYS)] = core_outcomes.DEFAULT_DAYS,
    limit: Annotated[int, Query(ge=1, le=core_outcomes.MAX_ROWS)] = core_outcomes.DEFAULT_ROWS,
) -> dict[str, Any]:
    """What the platform DID to the business: irreversible transactions, counted off the log.

    → `{"tenant": str|null, "project": str|null, "days": int,
         "since": float, "until": float,
         "totals": {"transactions": int, "confirmed": int, "failed": int, "sessions": int},
         "verbs": [{"verb": str, "count": int, "confirmed": int, "failed": int, "pending": int}],
         "series": [{"day": "YYYY-MM-DD", "total": int, "verbs": {str: int}}],
         "rows": [{"session": str, "tenant": str, "project": str, "channel": str,
                   "seq": int, "at": float, "day": str, "verb": str,
                   "confirmed": bool, "status": "done"|"failed"|"pending",
                   "summary": str|null}]}`

    A transaction is one `tool.call` whose `side_effect` is `irreversible` —
    the verb is the tool's own name and nothing here knows which names exist,
    so a project that declares a new irreversible tool appears on this board
    the first time it runs. `confirmed` is whether a `confirm.granted` for that
    tool stood unspent before the call: the caller's yes, paired one to one.

    `summary` is the line the tool's own `result_summary` rendered and the
    session's PII mask scrubbed, reused verbatim; it is null for a tool that
    declares no renderer and for one that failed. Nothing is re-rendered here.

    `series` covers every day of the window, empty days included, so a bar
    strip has a stable axis; `rows` is newest first and capped by `limit`.
    There is no rollup table — see `core/outcomes.py` for why.
    """
    return core_outcomes.outcomes(store, tenant=tenant, project=project, days=days, limit=limit)


@router.get("/reservations")
async def reservations(
    store: Reader,
    tenant: str,
    project: str,
    days: Annotated[int, Query(ge=1, le=business.MAX_DAYS)] = business.DEFAULT_DAYS,
    limit: Annotated[int, Query(ge=1, le=business.MAX_ROWS)] = business.DEFAULT_ROWS,
) -> dict[str, Any]:
    """The reservations THEMSELVES, read off the customer's own system — not off our log.

    → `{"tenant": str, "project": str, "days": int, "shape": str|null,
         "labels": {str: str|null}, "systems": [str],
         "rows": [{"id": str, "who": str, "contact": str|null, "when": str|null,
                   "handled_by": str|null, "state": str,
                   "tone": "new"|"changed"|"gone"|"plain",
                   "detail": str|null, "at": float|null, "session": str|null,
                   "verb": str|null, "confirmed": bool, "channel": str|null}],
         "views": [{"shape": …, "labels": …, "systems": …, "rows": […]}]}`

    `views` is one entry per system of this tenant that offers a record view,
    in the order the tenant's own factory builds them, and the flat `shape`,
    `labels`, `systems` and `rows` are the first of them. A shop that keeps its
    orders in one system and its incidents in another answers with two, each
    with its own shape and its own words for a state — they are two tables and
    not a longer one, and deciding which of a business's vocabularies wins is
    not the platform's to do.

    `/outcomes` counts what the platform DID, off the append-only log whose
    summaries are PII-filtered by design. This is the other reading and the one
    an operator asked for: who is coming, when, with whom, and whether that
    booking still stands. A patient's name is not in our log and must not be —
    it is in the clinic's booking system, which is where this goes to get it
    (`core.registry` → the tenant's adapters → `list_records`).

    `shape` is the business's own word for its records (`appointments`,
    `orders`) and `labels` its own column headings: a project whose systems
    offer no such view answers `shape: null` with no rows, and the console says
    so rather than drawing an agenda nobody has. Nothing in `core` or in the UI
    holds a list of shapes, columns or state words.

    `state` is the business's word for how a record stands and `tone` the only
    presentational field, decided by the adapter that knows what its own words
    mean. `session`, `verb` and `confirmed` are the join with `/outcomes`: the
    call that last touched this record inside the window, matched on the
    identifier the log's summary carries verbatim. Null means no call in the
    window touched it — see `core/business.py` for why that join is on an id
    and not on a name.
    """
    known = load_registry().get(tenant)
    if known is None:
        raise HTTPException(404, f"unknown tenant {tenant!r}; known: {sorted(load_registry())}")
    if project not in known.projects:
        detail = f"tenant {tenant!r} has no project {project!r}; known: {sorted(known.projects)}"
        raise HTTPException(404, detail)
    return await business.records(known, project, store, days=days, limit=limit)
