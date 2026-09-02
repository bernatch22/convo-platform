"""TenantContext: everything a session knows about who it serves.

Decisions: docs/decisions/convo.domain.context.md
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from convo.domain.catalog import ToolCatalog
from convo.domain.contracts import Channel

if TYPE_CHECKING:  # avoid import cycles; these are filled in by later milestones
    from convo.adapters.base import Adapter
    from convo.state.log import EventLog
    from convo.tools.confirm import ConfirmationToken
    from convo.tools.executor import ToolExecutor


@dataclass
class Tenant:
    """A customer of the platform: providers, region, data policy, projects."""

    id: str
    name: str
    region: str = "eu"
    projects: dict[str, "Project"] = field(default_factory=dict)

    def build_adapters(self) -> dict[str, "Adapter"]:
        """The customer's own systems, one adapter each, built fresh per session."""
        return {}


@dataclass
class Project:
    """A use case of a tenant: prompts, voice, tools, failure sentences, entry agent."""

    id: str
    name: str
    voice: str | None = None
    # One stage, one voice: {"TicketDesk": "<elevenlabs id>"}. A stage not named here
    # speaks with `voice`. A handoff to a desk with its own voice is the caller hearing
    # somebody else pick up, which is what a handoff IS — so the voice belongs to the
    # project's data like every other one, never to the stage's code.
    stage_voices: dict[str, str] = field(default_factory=dict)
    tts_model: str | None = None  # None = the platform default; see core/providers/tts.py
    stt_provider: str = "soniox"  # soniox | deepgram; see core/providers/stt.py
    llm_model: str | None = None  # None = the platform default; see core/providers/llm.py
    language: str = "es"
    greeting: str = ""  # spoken verbatim on session start (no LLM turn); "" = the model opens
    keyterms: list[str] = field(default_factory=list)
    backchannels: list[str] = field(default_factory=list)  # [] = the Spanish default
    stt_gate: dict[str, float] = field(default_factory=dict)  # {} = the platform's thresholds
    tools: ToolCatalog = field(default_factory=ToolCatalog)
    messages: dict[str, str] = field(default_factory=dict)
    knowledge_seed: str = ""
    knowledge_tag: str = "knowledge"  # the XML tag the knowledge block is wrapped in
    prompts: Path | None = None  # the project's prompts/ directory: one Markdown view per stage
    transfer_number: str | None = None  # E.164; None/"" = the agent is offered no transfer
    scoring: bool = True  # False = this project's finished calls are never scored (ms-13)
    recording: bool = True  # False = this project's calls keep no audio at all (ms-17)

    def knowledge(self, tc: "TenantContext") -> str:
        """The stable knowledge block a prompt opens with: the pinned override, else git's seed."""
        return tc.knowledge_override or self.knowledge_seed


@dataclass
class TenantContext:
    """Per-session context: tenant, project, channel, identifiers and collaborators."""

    tenant: Tenant
    project: Project
    channel: Channel
    session_id: str
    git_sha: str
    project_version: str
    today: date = field(default_factory=date.today)
    adapters: dict[str, "Adapter"] = field(default_factory=dict)
    tools: "ToolExecutor | None" = None
    log: "EventLog | None" = None
    confirmation_token: "ConfirmationToken | None" = None
    knowledge_override: str | None = None
    date_noted: bool = False  # the session-start date note is written once, by the entry stage
    clock: "Callable[[], datetime] | None" = None  # tests freeze it; None = the machine's clock
    customer: dict[str, Any] | None = None
    pii_values: set[str] = field(default_factory=set)
    prev_agent: Any = None
    # The live session's supervision state (`core.security.control.SupervisorControl`),
    # or None where no second human can reach the call: the console, a harness,
    # an offline eval. Every stage carries it because every stage may be the one
    # holding the floor when a human takes the line.
    supervisor: Any = None

    def now(self) -> time:
        """The time of day this session believes it is; tests freeze it through `clock`."""
        return (self.clock() if self.clock else datetime.now()).time()

    def label(self) -> str:
        """Short identifier for logs: `tenant/project#session`."""
        return f"{self.tenant.id}/{self.project.id}#{self.session_id}"
