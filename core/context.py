"""TenantContext: everything a session knows about who it serves.

One definition, built once per job by `core.router.resolve`, carried as the
session's `userdata` and reachable from every tool as `ctx.userdata`.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.contracts import Channel
from core.tools.catalog import ToolCatalog

if TYPE_CHECKING:  # avoid import cycles; these are filled in by later milestones
    from core.adapters.base import Adapter
    from core.tools.executor import ToolExecutor


@dataclass
class Tenant:
    """A customer of the platform: providers, region, data policy, projects."""

    id: str
    name: str
    region: str = "eu"
    projects: dict[str, "Project"] = field(default_factory=dict)


@dataclass
class Project:
    """A use case of a tenant: prompts, voice, tools, entry agent."""

    id: str
    name: str
    voice: str | None = None
    language: str = "es"
    keyterms: list[str] = field(default_factory=list)
    tools: ToolCatalog = field(default_factory=ToolCatalog)


@dataclass
class TenantContext:
    """Per-session context: tenant, project, channel, identifiers and collaborators."""

    tenant: Tenant
    project: Project
    channel: Channel
    session_id: str
    git_sha: str
    project_version: str
    adapters: dict[str, "Adapter"] = field(default_factory=dict)
    tools: "ToolExecutor | None" = None
    customer: dict[str, Any] | None = None
    prev_agent: Any = None

    def label(self) -> str:
        """Short identifier for logs: `tenant/project#session`."""
        return f"{self.tenant.id}/{self.project.id}#{self.session_id}"
