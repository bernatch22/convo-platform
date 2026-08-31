"""TenantContext: everything a session knows about who it serves.

One definition, built once per job by `core.router.resolve`, carried as the
session's `userdata` and reachable from every tool as `ctx.userdata`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from core.contracts import Channel
from core.tools.catalog import ToolCatalog

if TYPE_CHECKING:  # avoid import cycles; these are filled in by later milestones
    from core.adapters.base import Adapter
    from core.confirm import ConfirmationToken
    from core.state.log import EventLog
    from core.tools.executor import ToolExecutor


@dataclass
class Tenant:
    """A customer of the platform: providers, region, data policy, projects."""

    id: str
    name: str
    region: str = "eu"
    projects: dict[str, "Project"] = field(default_factory=dict)

    def build_adapters(self) -> dict[str, "Adapter"]:
        """The customer's own systems, one adapter each, built fresh per session.

        A tenant that has none keeps the default: it simply cannot run tools.
        Subclasses in `tenants/<id>/tenant.py` override it — core never imports
        a customer's code, so the factory has to travel on the tenant itself.
        """
        return {}


@dataclass
class Project:
    """A use case of a tenant: prompts, voice, tools, failure sentences, entry agent.

    `messages` overrides the platform's user-facing tool-failure sentences
    (`core.tools.messages`) in the project's own register and language.
    `backchannels` overrides the murmurs a barge-in filter ignores
    (`core.barge_in.SPANISH_BACKCHANNELS`) — data, so core knows one language.
    `stt_gate` overrides how much voiced audio a transcript must have behind it
    to be believed (`core.stt_gate.GateOptions`), for a tenant on a noisier line.

    The fields named in `core.state.overrides.OVERRIDABLE` are the ones a
    supervisor may change from the console without a deploy: `core.state.overrides`
    replaces them on the way out of the router (`core.state.store.PipelineOverride`).
    `llm_model` is which model answers for this project. The LLM is a swappable
    interface driver, so it is project data like the voice and not a constant in
    `core/providers`, and an eval can measure a second model on the same goldens
    (`core.testing.report --model`) without editing one of them.
    `scoring` is the post-call score's opt-out (ms-13). A project that sets it
    to False is never judged after a call ends and its sessions show a dash
    where the others show a chip — which is a business decision (a queue whose
    calls are two sentences long, a tenant that has not agreed to it), so it
    lives with the project's data and not in an environment variable.
    """

    id: str
    name: str
    voice: str | None = None
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
    scoring: bool = True  # False = this project's finished calls are never scored (ms-13)

    def knowledge(self, tc: "TenantContext") -> str:
        """The stable knowledge block a prompt opens with: the pinned override, else git's seed.

        Git is the seed every deploy carries; a row in `project_versions` can
        override it without a deploy, and the version the session ran with is
        in its first log event either way.
        """
        return tc.knowledge_override or self.knowledge_seed


@dataclass
class TenantContext:
    """Per-session context: tenant, project, channel, identifiers and collaborators.

    `today` is the calendar day the conversation happens on. It lives here and
    never in the system prompt: Haiku 4.5 only caches a prefix of 4096+ tokens
    and only while that prefix is byte-identical, so a date in the instructions
    would throw the cache away on every new day. Tools that read "el jueves"
    resolve it against this instead.

    `pii_values` is the session's own PII, learned by the executor from the
    `pii_scope` arguments of every tool call and from `customer`. It is what
    lets a log line mask a name that arrived inside a free-text argument no
    contract describes — see `core.tools.guard.mask`.
    """

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
