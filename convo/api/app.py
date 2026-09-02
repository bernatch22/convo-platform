"""Control plane: the HTTP door a client knocks on before any room exists.

Decisions: docs/decisions/convo.api.app.md
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
    """Seed the phone routes this deploy owns, then run the post-call scorer beside the API."""
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
