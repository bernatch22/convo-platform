"""What this deployment serves: every routable tenant and its projects."""

from fastapi import APIRouter

from convo.session.registry import load_registry

router = APIRouter()


@router.get("/tenants")
def tenants() -> list[dict]:
    """What this deployment serves: every routable tenant and its projects.

    → `[{"tenant": str, "projects": [{"id", "name", "voice", "language"}]}]`
    """
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
