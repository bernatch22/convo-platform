"""Control plane: the HTTP door a client knocks on before any room exists.

The worker never opens a database or takes a business decision; this process
does. One router per resource under `convo/api/`; every handler opens its own
store (docs/decisions/004-one-store-per-request.md).

    convo api   # or: uvicorn convo.api.app:app --port 8090
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from convo.api import evals, pipeline, reservations, sessions, supervise, tenants, tokens
from convo.api.deps import evals_runner, open_store
from convo.api.webui import mount_ui
from convo.scoring import sweeper
from convo.state.store import SQLiteStore
from convo.telephony import lines as phone_lines

__all__ = ["app", "evals_runner", "open_store"]


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Seed the phone routes this deploy owns, then run the post-call scorer beside the API.

    The seed runs once, at startup, and only writes a number the store does not
    already carry (`core.telephony.lines.seed`): the control plane owns the
    number → project table, so a fresh database must not answer "no line" for a
    number that has been ringing for weeks.

    The sweeper is a task of this process and not a cron entry because it must
    stop when the control plane stops: a sweeper still judging calls against a
    database whose owner has gone is spending money nobody is watching.
    `SCORING_SWEEP=0` starts nothing at all.
    """
    phone_lines.seed(SQLiteStore())
    if not sweeper.enabled():
        yield
        return
    task = asyncio.create_task(sweeper.run())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="convo control plane", lifespan=lifespan)

for resource in (tokens, tenants, sessions, reservations, supervise, pipeline, evals):
    app.include_router(resource.router)

# Last, always: the SPA catch-all must not shadow an endpoint declared above it.
UI_IS_BUILT = mount_ui(app)
