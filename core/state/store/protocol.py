"""The rows a store keeps and the verbs every backend implements; nothing above them knows SQL."""

from dataclasses import dataclass
from typing import Any, Protocol

from core.state.events import Event


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


@dataclass(frozen=True)
class Route:
    """Which tenant and project answer a key (a phone number, a room prefix) on a fleet."""

    fleet: str
    key: str
    tenant: str
    project: str
    channel: str = "voice"


@dataclass(frozen=True)
class PipelineOverride:
    """One field of a project's pipeline set from the console instead of from git.

    Voice, TTS model and greeting are the three a supervisor changes between
    calls; the row is what makes the change survive without a deploy. The read
    is one row per field, so the console can show when each was last touched.
    """

    tenant: str
    project: str
    field: str
    value: str
    updated_at: float = 0.0


@dataclass(frozen=True)
class ProjectVersion:
    """A pinned prompt version: git is the seed, this row is the override the box serves."""

    tenant: str
    project: str
    version: str
    knowledge_override: str | None = None
    created_at: float = 0.0


class Store(Protocol):
    """Sessions and their events, plus the three small tables the router reads."""

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

    def route(self, fleet: str, key: str) -> Route | None:
        """The route registered for this key on this fleet, or None."""
        ...

    def add_route(self, route: Route) -> None:
        """Register (or replace) a route."""
        ...

    def routes(self) -> list[Route]:
        """Every route, sorted by fleet and key."""
        ...

    def pinned_version(self, tenant: str, project: str) -> ProjectVersion | None:
        """The version pinned for a project, or None when git is the only source."""
        ...

    def pin_version(self, version: ProjectVersion) -> None:
        """Pin a version (replacing the previous pin for that project)."""
        ...

    def versions(self) -> list[ProjectVersion]:
        """Every pinned version, sorted by tenant and project."""
        ...

    def pipeline_overrides(self, tenant: str, project: str) -> list[PipelineOverride]:
        """The console's overrides for one project, one row per field, sorted by field."""
        ...

    def set_pipeline_override(self, override: PipelineOverride) -> None:
        """Set (or replace) one overridden field of a project's pipeline."""
        ...
