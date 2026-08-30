"""resolve: from a job to the one TenantContext it serves.

Four places can name the tenant, read in this order and the first that
answers wins:

1. `ctx.job.metadata` — the dispatcher's JSON (`SessionMeta`): a web token or
   an explicit dispatch names tenant, project and channel outright.
2. `ctx.job.attributes` — `convo.tenant` / `convo.project` (`convo.channel`)
   set on the dispatch by the control plane.
3. the SIP participant's attributes — `sip.trunkPhoneNumber` (the number the
   caller dialled) looked up in the `routes` table for this fleet; a phone
   number is a route, never a project.
4. the environment — `TENANT` / `PROJECT`, the console's way of choosing.

The channel travels with the session (voice for SIP, chat when the attributes
say so), never with the project. A tenant whose import failed is simply not in
the registry: unroutable, not fatal.
"""

import os
import subprocess
from datetime import date
from typing import Any

from core.context import TenantContext
from core.contracts import SessionMeta
from core.registry import load_registry
from core.state.attach import attach_log
from core.state.store import SQLiteStore, Store
from core.tools.executor import attach_local_tools

TENANT_ATTR = "convo.tenant"
PROJECT_ATTR = "convo.project"
CHANNEL_ATTR = "convo.channel"
SIP_NUMBER_ATTRS = ("sip.trunkPhoneNumber", "sip.phoneNumber")
DEFAULT_TENANT = "clinica-norte"
DEFAULT_PROJECT = "reagendamiento"


class UnroutableTenant(LookupError):
    """The job names a tenant or project this worker cannot serve."""


async def resolve(ctx: Any, store: Store | None = None) -> TenantContext:
    """Read who this job is for, build the wired context, pin the prompt version.

    Wired means the tenant's adapters are built, an executor sits over them and
    the session log is open: a context handed to a session must be able to run
    the tools its project declares, or the model calls into a void.
    """
    store = store or SQLiteStore()
    meta = session_meta(ctx, store)
    registry = load_registry()
    tenant = registry.get(meta.tenant)
    if tenant is None:
        raise UnroutableTenant(f"unknown tenant {meta.tenant!r}; known: {sorted(registry)}")
    project = tenant.projects.get(meta.project)
    if project is None:
        raise UnroutableTenant(f"tenant {meta.tenant!r} has no project {meta.project!r}")
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
    return attach_log(attach_local_tools(tc), store)


def session_meta(ctx: Any, store: Store) -> SessionMeta:
    """Who the session is for, from the first source that names it (see the module docstring)."""
    raw = (ctx.job.metadata or "").strip()
    if raw:
        return SessionMeta.model_validate_json(raw)
    attributes = _attributes(ctx)
    if TENANT_ATTR in attributes:
        return SessionMeta(
            tenant=attributes[TENANT_ATTR],
            project=attributes.get(PROJECT_ATTR, DEFAULT_PROJECT),
            channel=attributes.get(CHANNEL_ATTR, "chat"),
        )
    number = _dialled_number(ctx)
    if number:
        route = store.route(os.getenv("FLEET", "cc"), number)
        if route is None:
            raise UnroutableTenant(f"no route for {number!r} on this fleet")
        return SessionMeta(tenant=route.tenant, project=route.project, channel=route.channel)
    return SessionMeta(
        tenant=os.getenv("TENANT", DEFAULT_TENANT),
        project=os.getenv("PROJECT", DEFAULT_PROJECT),
        channel="chat",
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


def _dialled_number(ctx: Any) -> str | None:
    """The number a SIP caller dialled, from the participant the job was created for."""
    participant = getattr(ctx.job, "participant", None)
    attributes = dict(getattr(participant, "attributes", None) or {})
    for name in SIP_NUMBER_ATTRS:
        if attributes.get(name):
            return attributes[name]
    return None
