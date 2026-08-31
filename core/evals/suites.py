"""Which pytest target a project's eval suite names — read off disk, never imported.

A project declares its suites in `tenants/<id>/projects/<id>/evals/suites.json`:

    {"ring1": "tests/evals/test_reception_deepeval.py"}

The key is free text on purpose. Ring 1 today, personas tomorrow: a new suite is
one line of a customer's own data, never a branch in `core`. The file is read,
never imported, so this module keeps the rule the whole runtime keeps — `core`
does not know any tenant exists.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TENANTS_DIR = REPO_ROOT / "tenants"
SUITES_FILE = "suites.json"

# Tenant and project ids arrive over HTTP; only these can name a folder.
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class UnknownSuite(LookupError):
    """No such suite is declared for that project — the message names what is."""


def declared(tenant: str, project: str) -> dict[str, str]:
    """Every suite this project declares, suite id -> pytest target; empty when it declares none."""
    path = _suites_path(tenant, project)
    if path is None or not path.is_file():
        return {}
    try:
        found = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return {k: v for k, v in found.items() if isinstance(k, str) and isinstance(v, str)}


def target(tenant: str, project: str, suite: str) -> str:
    """The pytest path `deepeval test run` gets, or `UnknownSuite` naming what is declared."""
    suites = declared(tenant, project)
    if suite not in suites:
        known = sorted(suites) or ["(none declared)"]
        raise UnknownSuite(f"{tenant}/{project} has no suite {suite!r}; declared: {known}")
    return suites[suite]


def _suites_path(tenant: str, project: str) -> Path | None:
    """Where the declaration lives, or None when either id could not name a folder."""
    if not (SAFE_ID.match(tenant) and SAFE_ID.match(project)):
        return None
    return TENANTS_DIR / tenant / "projects" / project / "evals" / SUITES_FILE
