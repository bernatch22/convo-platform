"""Store: where session logs live. A Protocol, an in-memory store for tests, SQLite for the box.

The SQLite store is built to survive the one failure that matters for an
audit log — the process dying mid-call. WAL journaling with `synchronous=FULL`
makes every `append` durable when it returns, and two triggers refuse UPDATE
and DELETE on `events`, so the table cannot be edited even by a well-meaning
migration. Postgres later is this same interface over a pool in `api.py`;
the job process never opens a database of its own in production (it talks to
the control plane), but on a laptop the file is the control plane.
"""

import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from core.state.events import Event

DEFAULT_DB = "tmp/convo.db"
DB_ENV = "CONVO_DB"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, tenant TEXT NOT NULL, project TEXT NOT NULL, channel TEXT NOT NULL,
  started_at REAL NOT NULL, ended_at REAL, outcome TEXT, report_json TEXT
);
CREATE TABLE IF NOT EXISTS events (
  session_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL, t_ms INTEGER NOT NULL,
  payload_json TEXT NOT NULL, PRIMARY KEY (session_id, seq)
) WITHOUT ROWID;
CREATE TRIGGER IF NOT EXISTS events_append_only_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_append_only_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;
"""


@dataclass
class SessionRow:
    """What the store knows about one session besides its events."""

    id: str
    tenant: str
    project: str
    channel: str
    started_at: float
    ended_at: float | None = None
    outcome: str | None = None
    report: dict[str, Any] | None = None
    event_count: int = 0


class Store(Protocol):
    """The five verbs every backend implements; nothing above them knows SQL."""

    def open_session(self, row: SessionRow) -> None:
        """Register a session before its first event."""
        ...

    def append(self, session_id: str, event: Event) -> None:
        """Persist one event durably; must not return before it is safe."""
        ...

    def close_session(self, session_id: str, outcome: str, report: dict[str, Any] | None) -> None:
        """Mark the end: outcome and the framework's session report."""
        ...

    def sessions(self) -> list[SessionRow]:
        """Every session, newest first, with its event count."""
        ...

    def session(self, session_id: str) -> SessionRow | None:
        """One session's row, or None."""
        ...

    def events(self, session_id: str) -> list[Event]:
        """The session's events in seq order."""
        ...


@dataclass
class MemoryStore:
    """Dicts and lists: the store tests and the harness use; nothing survives the process."""

    rows: dict[str, SessionRow] = field(default_factory=dict)
    log: dict[str, list[Event]] = field(default_factory=dict)

    def open_session(self, row: SessionRow) -> None:
        self.rows[row.id] = row
        self.log.setdefault(row.id, [])

    def append(self, session_id: str, event: Event) -> None:
        self.log.setdefault(session_id, []).append(event)

    def close_session(self, session_id: str, outcome: str, report: dict[str, Any] | None) -> None:
        row = self.rows[session_id]
        row.outcome, row.report = outcome, report

    def sessions(self) -> list[SessionRow]:
        rows = sorted(self.rows.values(), key=lambda r: r.started_at, reverse=True)
        for row in rows:
            row.event_count = len(self.log.get(row.id, []))
        return rows

    def session(self, session_id: str) -> SessionRow | None:
        return self.rows.get(session_id)

    def events(self, session_id: str) -> list[Event]:
        return list(self.log.get(session_id, []))


class SQLiteStore:
    """The laptop's and the dev box's store: one file, durable per append, append-only by trigger."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or os.getenv(DB_ENV, DEFAULT_DB))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)

    def open_session(self, row: SessionRow) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO sessions (id, tenant, project, channel, started_at) "
            "VALUES (?,?,?,?,?)",
            (row.id, row.tenant, row.project, row.channel, row.started_at),
        )

    def append(self, session_id: str, event: Event) -> None:
        self.db.execute(
            "INSERT INTO events (session_id, seq, kind, t_ms, payload_json) VALUES (?,?,?,?,?)",
            (session_id, event.seq, event.kind, event.t_ms, _dumps(event.payload)),
        )

    def close_session(self, session_id: str, outcome: str, report: dict[str, Any] | None) -> None:
        self.db.execute(
            "UPDATE sessions SET ended_at=strftime('%s','now'), outcome=?, report_json=? "
            "WHERE id=?",
            (outcome, _dumps(report) if report is not None else None, session_id),
        )

    def sessions(self) -> list[SessionRow]:
        cursor = self.db.execute(
            "SELECT s.id, s.tenant, s.project, s.channel, s.started_at, s.ended_at, s.outcome, "
            "(SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) "
            "FROM sessions s ORDER BY s.started_at DESC"
        )
        return [SessionRow(*r[:7], report=None, event_count=r[7]) for r in cursor]

    def session(self, session_id: str) -> SessionRow | None:
        row = self.db.execute(
            "SELECT id, tenant, project, channel, started_at, ended_at, outcome, report_json "
            "FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        report = json.loads(row[7]) if row[7] else None
        return SessionRow(*row[:7], report=report, event_count=len(self.events(session_id)))

    def events(self, session_id: str) -> list[Event]:
        cursor = self.db.execute(
            "SELECT seq, kind, t_ms, payload_json FROM events WHERE session_id=? ORDER BY seq",
            (session_id,),
        )
        return [Event(seq=s, kind=k, t_ms=t, payload=json.loads(p)) for s, k, t, p in cursor]


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
