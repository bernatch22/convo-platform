"""resolve: from a job to the one TenantContext it serves.

Decisions: docs/decisions/convo.session.router.md
"""

import os
import subprocess
from datetime import date
from typing import Any

from convo import settings
from convo.domain.context import TenantContext
from convo.domain.contracts import SessionMeta
from convo.session.registry import load_registry
from convo.session.sip import caller_attributes, dialled_number
from convo.state import overrides
from convo.state.attach import attach_log
from convo.state.store import SQLiteStore, Store
from convo.tools.executor import attach_local_tools

TENANT_ATTR = "convo.tenant"
PROJECT_ATTR = "convo.project"
CHANNEL_ATTR = "convo.channel"
TENANT_ENV = "TENANT"


class UnroutableTenant(LookupError):
    """The job names a tenant or project this worker cannot serve."""


async def resolve(ctx: Any, store: Store | None = None) -> TenantContext:
    """Read who this job is for, build the wired context, pin the prompt version."""
    store = store or SQLiteStore()
    sip = await caller_attributes(ctx, wait_s=0.0 if os.getenv(TENANT_ENV) else None)
    meta = session_meta(ctx, store, sip)
    registry = load_registry()
    tenant = registry.get(meta.tenant)
    if tenant is None:
        raise UnroutableTenant(f"unknown tenant {meta.tenant!r}; known: {sorted(registry)}")
    project = tenant.projects.get(meta.project)
    if project is None:
        raise UnroutableTenant(f"tenant {meta.tenant!r} has no project {meta.project!r}")
    project = overrides.apply(tenant.id, project, store)
    pinned = store.pinned_version(tenant.id, project.id)
    tc = TenantContext(
        tenant=tenant,
        project=project,
        channel=meta.channel,
        session_id=ctx.job.id,
        git_sha=git_sha(),
        project_version=meta.project_version or (pinned.version if pinned else f"git:{git_sha()}"),
        knowledge_override=pinned.knowledge_override if pinned else None,
        today=date.today(),
    )
    return attach_log(attach_local_tools(tc), store, sip=sip)


def session_meta(ctx: Any, store: Store, sip: dict[str, str] | None = None) -> SessionMeta:
    """Who the session is for, from the first source that names it (see the module docstring)."""
    raw = (ctx.job.metadata or "").strip()
    if raw:
        return SessionMeta.model_validate_json(raw)
    attributes = _attributes(ctx)
    if TENANT_ATTR in attributes:
        return SessionMeta(
            tenant=attributes[TENANT_ATTR],
            project=attributes.get(PROJECT_ATTR, settings.default_project()),
            channel=attributes.get(CHANNEL_ATTR, "chat"),
        )
    number = dialled_number(sip or {})
    if number:
        route = store.route(settings.fleet(), number)
        if route is None:
            raise UnroutableTenant(f"no route for {number!r} on this fleet")
        return SessionMeta(tenant=route.tenant, project=route.project, channel=route.channel)
    # a console with a microphone IS a voice session: the env fallback is voice
    return SessionMeta(
        tenant=os.getenv(TENANT_ENV, settings.default_tenant()),
        project=os.getenv("PROJECT", settings.default_project()),
        channel="voice",
    )


def git_sha() -> str:
    """Short SHA of the running code, pinned into every session."""
    try:
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        out = subprocess.run(cmd, capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def _attributes(ctx: Any) -> dict[str, str]:
    """The dispatch attributes, as a plain dict (the proto map is not one)."""
    return dict(getattr(ctx.job, "attributes", None) or {})
