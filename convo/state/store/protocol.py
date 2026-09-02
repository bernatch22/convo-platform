"""The rows a store keeps and the verbs every backend implements; nothing above them knows SQL."""

from dataclasses import dataclass
from typing import Any, Protocol

from convo.state.events import Event


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


@dataclass(frozen=True)
class MetricScore:
    """One metric's verdict over a whole eval run: its mean score and the cases it decided."""

    metric: str
    score: float
    passed: int = 0
    failed: int = 0


@dataclass(frozen=True)
class EvalRun:
    """One `deepeval` run of one project's suite: what it scored and where its evidence is.

    Stored the moment it starts (`status="running"`) so the console can watch it
    land, then replaced by id when it ends. `suite` is free text on purpose —
    ring 1 today, personas tomorrow — and nothing here knows which is which.
    """

    id: str
    tenant: str
    project: str
    suite: str
    status: str = "running"  # running | done | failed
    started_at: float = 0.0
    finished_at: float | None = None
    git_sha: str | None = None
    milestone: str | None = None
    metrics: tuple[MetricScore, ...] = ()
    report_html: str | None = None
    log_path: str | None = None
    detail: str | None = None


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

    def eval_runs(self) -> list[EvalRun]:
        """Every stored eval run, newest first."""
        ...

    def add_eval_run(self, run: EvalRun) -> None:
        """Store one eval run, replacing the row with the same id."""
        ...
