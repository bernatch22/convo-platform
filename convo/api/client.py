"""The read side of the control plane: stored sessions as the console reads them.

Decisions: docs/decisions/convo.api.client.md
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from convo.scoring.report import already_scored
from convo.session import recordings
from convo.session.rooms import EVAL_PREFIX
from convo.state.events import Event
from convo.state.store import SessionRow, Store

DEFAULT_LIMIT = 50
POLL_S = 0.3
KEEPALIVE_S = 10.0
END_KIND = "session.end"
PHONE_ATTRS = ("sip.phoneNumber", "sip.trunkPhoneNumber")


def sessions(
    store: Store,
    tenant: str | None = None,
    project: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """The session list, newest first: who it served, how it ended, what it cost."""
    rows = [row for row in store.sessions() if _matches(row, tenant, project)][:limit]
    return [_row_view(store, row) for row in rows]


def session(store: Store, session_id: str) -> dict[str, Any] | None:
    """One session in full: its row, the framework's end-of-call report, every event."""
    row = store.session(session_id)
    if row is None:
        return None
    events = store.events(session_id)
    view = _row_view(store, row, events)
    view["report"] = row.report
    view["events"] = [event_view(event) for event in events]
    return view


def event_view(event: Event) -> dict[str, Any]:
    """One log line as JSON: seq, offset, kind and the payload exactly as it was written."""
    return {"seq": event.seq, "t_ms": event.t_ms, "kind": event.kind, "payload": event.payload}


async def live(
    store: Store, session_id: str, after: int = 0, poll_s: float = POLL_S
) -> AsyncIterator[str]:
    """SSE frames for one session's events as they append, from `after` onwards."""
    row = store.session(session_id)
    if row is None:
        yield _frame("error", {"error": f"no session {session_id}"})
        return
    yield _frame("open", _row_view(store, row))
    last_seq, idle = after, 0.0
    while True:
        fresh = [e for e in store.events(session_id) if e.seq > last_seq]
        for event in fresh:
            last_seq, idle = event.seq, 0.0
            yield _frame("append", event_view(event))
            if event.kind == END_KIND:
                yield _frame("end", {"seq": event.seq, "outcome": event.payload.get("outcome")})
                return
        if not fresh:
            idle += poll_s
            if idle >= KEEPALIVE_S:
                idle = 0.0
                yield ": keepalive\n\n"
        await asyncio.sleep(poll_s)


def live_calls(store: Store, rooms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The SFU's live rooms, each matched — best effort — to the session that is logging it."""
    running = [row for row in store.sessions() if row.outcome is None]
    numbers = {row.id: _sip_number(store, row) for row in running}
    return [{**room, **_match(running, numbers, room)} for room in rooms]


def _match(running: list[SessionRow], numbers: dict[str, str | None], room: dict) -> dict:
    """Which stored session this room is, by project prefix or by the caller's number."""
    for row in running:
        named = room["room"].removeprefix(f"{EVAL_PREFIX}-")
        by_name = named.startswith(f"{row.tenant}-{row.project}-")
        by_phone = room.get("phone") is not None and numbers.get(row.id) == room["phone"]
        if by_name or by_phone:
            return {"session_id": row.id, "tenant": row.tenant, "project": row.project}
    return {"session_id": None, "tenant": None, "project": None}


def _sip_number(store: Store, row: SessionRow) -> str | None:
    """The number this session was called on, off its `session.start` event."""
    return _phone_of(store.events(row.id))


def _phone_of(events: list[Event]) -> str | None:
    """The caller's number, or the trunk's when the caller withheld it; None when not a call."""
    for event in events:
        sip = event.payload.get("sip") or {}
        for attribute in PHONE_ATTRS:
            if sip.get(attribute):
                return str(sip[attribute])
        return None
    return None


def _matches(row: SessionRow, tenant: str | None, project: str | None) -> bool:
    return (tenant is None or row.tenant == tenant) and (project is None or row.project == project)


def _row_view(store: Store, row: SessionRow, events: list[Event] | None = None) -> dict[str, Any]:
    """The list line: identity, envelope, and the two numbers read off the log itself."""
    events = store.events(row.id) if events is None else events
    return {
        "id": row.id,
        "tenant": row.tenant,
        "project": row.project,
        "channel": row.channel,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "outcome": row.outcome,
        "events": len(events),
        "turns": sum(1 for e in events if e.kind.startswith("turn.")),
        "cost_eur": _cost(events),
        "phone": _phone_of(events),
        "score": already_scored(events),
        "audio": recordings.for_session(row.id) is not None,
    }


def _cost(events: list[Event]) -> float | None:
    """What the close event priced the call at, or None while the call is still running."""
    for event in reversed(events):
        if event.kind == END_KIND:
            cost = event.payload.get("cost") or {}
            return cost.get("eur") if isinstance(cost, dict) else None
    return None


def _frame(name: str, data: dict[str, Any]) -> str:
    """One SSE frame: an event name and a single JSON line, as the browser's EventSource wants."""
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
