"""What every handler shares: one store per request, the eval runner, the SSE headers."""

from typing import Annotated

from fastapi import Depends, HTTPException

from convo.domain.context import Project, Tenant
from convo.evals.runner import EvalRunner
from convo.session.registry import load_registry
from convo.state import overrides
from convo.state.store import SQLiteStore, Store

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def open_store() -> Store:
    """One store per request, opened in the coroutine that reads it (see the module docstring)."""
    return SQLiteStore()


# The store every handler reads, injected so a test can seed a MemoryStore.
Reader = Annotated[Store, Depends(open_store)]


def effective(tenant: str, project: str, store: Store) -> tuple[Tenant, Project]:
    """The registry's tenant and its project with the stored overrides already applied."""
    known = load_registry().get(tenant)
    if known is None:
        raise HTTPException(404, f"unknown tenant {tenant!r}; known: {sorted(load_registry())}")
    found = known.projects.get(project)
    if found is None:
        detail = f"tenant {tenant!r} has no project {project!r}; known: {sorted(known.projects)}"
        raise HTTPException(404, detail)
    return known, overrides.apply(tenant, found, store)


# One runner per process, because "one run at a time" is a property of the BOX,
# not of a request. It opens its own store: it outlives the request that
# started it and a per-request connection would be closed under it.
EVAL_RUNNER = EvalRunner(SQLiteStore)


def evals_runner() -> EvalRunner:
    """This box's single eval slot, injected so a test can hand in a runner with a fake launcher."""
    return EVAL_RUNNER


Runner = Annotated[EvalRunner, Depends(evals_runner)]
