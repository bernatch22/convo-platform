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
    `llm_model` is which model answers for this project. The LLM is a swappable
    interface driver, so it is project data like the voice and not a constant in
    `core/providers`, and an eval can measure a second model on the same goldens
    (`core.testing.report --model`) without editing one of them.
    """

    id: str
    name: str
    voice: str | None = None
    tts_model: str | None = None  # None = the platform default; see core/providers/tts.py
    llm_model: str | None = None  # None = the platform default; see core/providers/llm.py
    language: str = "es"
    keyterms: list[str] = field(default_factory=list)
    backchannels: list[str] = field(default_factory=list)  # [] = the Spanish default
    tools: ToolCatalog = field(default_factory=ToolCatalog)
    messages: dict[str, str] = field(default_factory=dict)
    knowledge_seed: str = ""

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

    def now(self) -> time:
        """The time of day this session believes it is; tests freeze it through `clock`."""
        return (self.clock() if self.clock else datetime.now()).time()

    def label(self) -> str:
        """Short identifier for logs: `tenant/project#session`."""
        return f"{self.tenant.id}/{self.project.id}#{self.session_id}"
