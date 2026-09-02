"""Deploy-level settings read from the environment, with the defaults `.env.example` documents."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def fleet() -> str:
    """The agent name this worker registers as; a dispatch rule names it to reach this deploy."""
    return os.getenv("FLEET", "cc")


def default_tenant() -> str:
    """The tenant the console talks to when nothing else names one."""
    return os.getenv("DEFAULT_TENANT", "clinica-norte")


def default_project() -> str:
    """The project the console talks to when nothing else names one."""
    return os.getenv("DEFAULT_PROJECT", "reagendamiento")


def seed_routes_file() -> Path:
    """The JSON file of phone routes a fresh store is seeded with (infra/seed/routes.json)."""
    return Path(os.getenv("CONVO_SEED_ROUTES", REPO_ROOT / "infra" / "seed" / "routes.json"))
