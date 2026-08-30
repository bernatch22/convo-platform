"""resolve: from a job to the TenantContext it serves."""

import os
import subprocess
from datetime import date

from livekit.agents import JobContext

from core.context import TenantContext
from core.contracts import SessionMeta
from core.registry import load_registry
from core.tools.executor import attach_local_tools


class UnroutableTenant(LookupError):
    """The job names a tenant or project this worker cannot serve."""


async def resolve(ctx: JobContext) -> TenantContext:
    """Read the dispatch metadata (or the console fallback) and build the wired context.

    Wired means the tenant's adapters are built and an executor sits over them:
    a context handed to a session must be able to run the tools its project
    declares, or the model calls into a void.
    """
    meta = _session_meta(ctx)
    registry = load_registry()
    tenant = registry.get(meta.tenant)
    if tenant is None:
        raise UnroutableTenant(f"unknown tenant {meta.tenant!r}; known: {sorted(registry)}")
    project = tenant.projects.get(meta.project)
    if project is None:
        raise UnroutableTenant(f"tenant {meta.tenant!r} has no project {meta.project!r}")
    tc = TenantContext(
        tenant=tenant,
        project=project,
        channel=meta.channel,
        session_id=ctx.job.id,
        git_sha=git_sha(),
        project_version=meta.project_version or f"git:{git_sha()}",
        today=date.today(),
    )
    return attach_local_tools(tc)


def git_sha() -> str:
    """Short SHA of the running code, pinned into every session."""
    try:
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        out = subprocess.run(cmd, capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def _session_meta(ctx: JobContext) -> SessionMeta:
    raw = (ctx.job.metadata or "").strip()
    if raw:
        return SessionMeta.model_validate_json(raw)
    # console mode / no dispatcher: the environment names the tenant
    return SessionMeta(
        tenant=os.getenv("TENANT", "clinica-norte"),
        project=os.getenv("PROJECT", "reagendamiento"),
        channel="chat",
    )
