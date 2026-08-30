"""MemoryStore: dicts and lists — what tests and the harness use; nothing survives the process."""

from dataclasses import dataclass, field
from typing import Any

from core.state.events import Event
from core.state.store.protocol import ProjectVersion, Route, SessionRow


@dataclass
class MemoryStore:
    """Every Store verb over plain dicts, in insertion order."""

    rows: dict[str, SessionRow] = field(default_factory=dict)
    log: dict[str, list[Event]] = field(default_factory=dict)
    routing: dict[tuple[str, str], Route] = field(default_factory=dict)
    pins: dict[tuple[str, str], ProjectVersion] = field(default_factory=dict)

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

    def route(self, fleet: str, key: str) -> Route | None:
        return self.routing.get((fleet, key))

    def add_route(self, route: Route) -> None:
        self.routing[(route.fleet, route.key)] = route

    def routes(self) -> list[Route]:
        return sorted(self.routing.values(), key=lambda r: (r.fleet, r.key))

    def pinned_version(self, tenant: str, project: str) -> ProjectVersion | None:
        return self.pins.get((tenant, project))

    def pin_version(self, version: ProjectVersion) -> None:
        self.pins[(version.tenant, version.project)] = version

    def versions(self) -> list[ProjectVersion]:
        return sorted(self.pins.values(), key=lambda v: (v.tenant, v.project))
