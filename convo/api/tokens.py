"""Session tickets: the JWT a client needs before any room exists."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from convo.api.auth import (
    mint_session,
)
from convo.domain.contracts import Channel, SessionMeta
from convo.session.registry import load_registry

router = APIRouter()


class TokenRequest(BaseModel):
    """What a client must say to open a session: who it wants to talk to, and how."""

    tenant: str
    project: str
    channel: Channel = "chat"
    user_id: str = "anonymous"


@router.post("/token")
def token(req: TokenRequest) -> dict[str, str]:
    """Validate the tenant/project against the registry and mint the session ticket.

    → `{"token": "<jwt>", "room": "<tenant>-<project>-<uuid>", "url": "<livekit ws url>"}`
    """
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
