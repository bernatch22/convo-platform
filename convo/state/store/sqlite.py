"""SQLiteStore: one file, durable per append, append-only by trigger — the laptop's control plane.

Decisions: docs/decisions/convo.state.store.sqlite.md
"""

import json
import os
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from convo.state.events import Event
from convo.state.store.protocol import (
    EvalRun,
    MetricScore,
    PipelineOverride,
    ProjectVersion,
    Route,
    SessionRow,
)

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
CREATE TABLE IF NOT EXISTS routes (
  fleet TEXT NOT NULL, key TEXT NOT NULL, tenant TEXT NOT NULL, project TEXT NOT NULL,
  channel TEXT NOT NULL, PRIMARY KEY (fleet, key)
);
CREATE TABLE IF NOT EXISTS project_versions (
  tenant TEXT NOT NULL, project TEXT NOT NULL, version TEXT NOT NULL,
  knowledge_override TEXT, created_at REAL NOT NULL, PRIMARY KEY (tenant, project)
);
CREATE TABLE IF NOT EXISTS pipeline_overrides (
  tenant TEXT NOT NULL, project TEXT NOT NULL, field TEXT NOT NULL, value TEXT NOT NULL,
  updated_at REAL NOT NULL, PRIMARY KEY (tenant, project, field)
);
CREATE TABLE IF NOT EXISTS eval_runs (
  id TEXT PRIMARY KEY, tenant TEXT NOT NULL, project TEXT NOT NULL, suite TEXT NOT NULL,
  status TEXT NOT NULL, started_at REAL NOT NULL, finished_at REAL, git_sha TEXT,
  milestone TEXT, metrics_json TEXT NOT NULL, report_html TEXT, log_path TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS eval_runs_by_start ON eval_runs (started_at DESC);
"""


class SQLiteStore:
    """Every Store verb over one SQLite file; the path comes from CONVO_DB or tmp/convo.db."""

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

    def route(self, fleet: str, key: str) -> Route | None:
        row = self.db.execute(
            "SELECT fleet, key, tenant, project, channel FROM routes WHERE fleet=? AND key=?",
            (fleet, key),
        ).fetchone()
        return Route(*row) if row else None

    def add_route(self, route: Route) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO routes (fleet, key, tenant, project, channel) "
            "VALUES (?,?,?,?,?)",
            (route.fleet, route.key, route.tenant, route.project, route.channel),
        )

    def routes(self) -> list[Route]:
        cursor = self.db.execute(
            "SELECT fleet, key, tenant, project, channel FROM routes ORDER BY fleet, key"
        )
        return [Route(*row) for row in cursor]

    def pinned_version(self, tenant: str, project: str) -> ProjectVersion | None:
        row = self.db.execute(
            "SELECT tenant, project, version, knowledge_override, created_at "
            "FROM project_versions WHERE tenant=? AND project=?",
            (tenant, project),
        ).fetchone()
        return ProjectVersion(*row) if row else None

    def pin_version(self, version: ProjectVersion) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO project_versions "
            "(tenant, project, version, knowledge_override, created_at) VALUES (?,?,?,?,?)",
            (
                version.tenant,
                version.project,
                version.version,
                version.knowledge_override,
                version.created_at or time.time(),
            ),
        )

    def versions(self) -> list[ProjectVersion]:
        cursor = self.db.execute(
            "SELECT tenant, project, version, knowledge_override, created_at "
            "FROM project_versions ORDER BY tenant, project"
        )
        return [ProjectVersion(*row) for row in cursor]

    def pipeline_overrides(self, tenant: str, project: str) -> list[PipelineOverride]:
        cursor = self.db.execute(
            "SELECT tenant, project, field, value, updated_at FROM pipeline_overrides "
            "WHERE tenant=? AND project=? ORDER BY field",
            (tenant, project),
        )
        return [PipelineOverride(*row) for row in cursor]

    def set_pipeline_override(self, override: PipelineOverride) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO pipeline_overrides "
            "(tenant, project, field, value, updated_at) VALUES (?,?,?,?,?)",
            (
                override.tenant,
                override.project,
                override.field,
                override.value,
                override.updated_at or time.time(),
            ),
        )

    def eval_runs(self) -> list[EvalRun]:
        cursor = self.db.execute(
            "SELECT id, tenant, project, suite, status, started_at, finished_at, git_sha, "
            "milestone, metrics_json, report_html, log_path, detail "
            "FROM eval_runs ORDER BY started_at DESC"
        )
        return [_run(row) for row in cursor]

    def add_eval_run(self, run: EvalRun) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO eval_runs (id, tenant, project, suite, status, started_at, "
            "finished_at, git_sha, milestone, metrics_json, report_html, log_path, detail) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run.id,
                run.tenant,
                run.project,
                run.suite,
                run.status,
                run.started_at or time.time(),
                run.finished_at,
                run.git_sha,
                run.milestone,
                _dumps([asdict(m) for m in run.metrics]),
                run.report_html,
                run.log_path,
                run.detail,
            ),
        )


def _run(row: tuple) -> EvalRun:
    """One eval_runs row back as the frozen dataclass, metrics parsed out of their JSON column."""
    metrics = tuple(MetricScore(**m) for m in json.loads(row[9]))
    return EvalRun(*row[:9], metrics=metrics, report_html=row[10], log_path=row[11], detail=row[12])


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
