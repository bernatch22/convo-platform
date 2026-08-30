"""Control plane: the HTTP door a client knocks on before any room exists.

The worker (`worker.py`) never opens a database or takes a business decision;
this process does. Today it holds the two endpoints ms-8 needs — mint a
session token with the agent dispatch inside it, and list what this deploy
can serve. Run it with:

    uv run uvicorn api:app --port 8090
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.auth import mint_session
from core.contracts import Channel, SessionMeta
from core.registry import load_registry

app = FastAPI(title="convo control plane")


class TokenRequest(BaseModel):
    """What a client must say to open a session: who it wants to talk to, and how."""

    tenant: str
    project: str
    channel: Channel = "chat"
    user_id: str = "anonymous"


@app.post("/token")
def token(req: TokenRequest) -> dict[str, str]:
    """Validate the tenant/project against the registry and mint the session ticket."""
    registry = load_registry()
    tenant = registry.get(req.tenant)
    if tenant is None:
        raise HTTPException(404, f"unknown tenant {req.tenant!r}; known: {sorted(registry)}")
    if req.project not in tenant.projects:
        known = sorted(tenant.projects)
        detail = f"tenant {req.tenant!r} has no project {req.project!r}; known: {known}"
        raise HTTPException(404, detail)
    meta = SessionMeta(tenant=req.tenant, project=req.project, channel=req.channel)
    return mint_session(meta, user_id=req.user_id)


@app.get("/tenants")
def tenants() -> list[dict]:
    """What this deployment serves: every routable tenant and its projects."""
    return [
        {
            "tenant": tenant.id,
            "projects": [
                {"id": p.id, "name": p.name, "voice": p.voice, "language": p.language}
                for p in tenant.projects.values()
            ],
        }
        for tenant in load_registry().values()
    ]
