"""What every suite of a project actually asks of the agent — read off disk, never imported.

A suite id is a project's own data (`evals/suites.json`); the cases it runs are
its own data too, and they live in two files next to it:

    goldens.json        one TURN each — the caller's line, the behaviour a
                        reviewer expects back, and the tools that must have run
    ring2_goldens.json  one CALL each — a persona, an objective, the lines the
                        caller says out loud, the hard policies that must
                        survive the call, and how many turns it gets

This module joins the two to the suites by the one name a run carries, so the
console can put "ring1 · 12 goldens" next to the runs of `ring1` and show what
those twelve actually are.

**How a suite is joined to its dataset.** `suites.json` gives a pytest target,
and that file NAMES the dataset it reads. So the target is read as text and
searched for the two filenames — never imported, never executed. A suite whose
target mentions neither (its cases are written in python, like a simulator's
personas) is reported with `dataset: null` and no goldens: the screen says
where they live instead of pretending they are not there.

Ring 2 is the one suite no project declares in `suites.json`: it is discovered
by convention (`evals/test_ring2.py`, the same convention `core.testing.nightly`
walks) and files its runs under the id `ring2`.

Everything here is a file read under `tenants/`, so `core` keeps the rule the
whole runtime keeps: it does not import any tenant module, and a project with a
broken `evals/` answers with an empty suite rather than a stack trace.
"""

import json
from pathlib import Path
from typing import Any

from core.evals.suites import SAFE_ID, TENANTS_DIR
from core.evals.suites import declared as declared_suites

TURN_DATASET = "goldens.json"
CALL_DATASET = "ring2_goldens.json"

RING2_SUITE = "ring2"  # the id a nightly files itself under
RING2_TARGET = "test_ring2.py"  # how a project declares it has a ring 2

REPO_ROOT = TENANTS_DIR.parent


class UnknownProject(LookupError):
    """No `evals/` folder on disk for that tenant and project — the endpoint answers 404."""


def datasets(tenant: str, project: str) -> dict[str, Any]:
    """Every suite this project can run, each with the goldens it reads and how many there are.

    → `{"tenant", "project", "suites": [{"suite", "target", "dataset", "kind",
    "count", "goldens": [...]}]}` — `kind` is `turn`, `call` or `code`, and
    `count` is null only for `code`, where the cases are not on disk.
    """
    folder = _evals_dir(tenant, project)
    if folder is None:
        raise UnknownProject(f"no evals on disk for project {tenant}/{project}")
    declared = sorted(declared_suites(tenant, project).items())
    suites = [_suite(folder, name, target) for name, target in declared]
    # The ones with cases to READ first: a suite whose goldens live in python has
    # nothing to show, and leading with it is leading with an apology.
    suites.sort(key=lambda suite: suite["kind"] == "code")
    return {"tenant": tenant, "project": project, "suites": suites + _ring2(folder)}


def turn_goldens(folder: Path) -> list[dict[str, Any]]:
    """The ring-1 goldens of a project: the caller's line and the behaviour expected back."""
    return [
        {
            "input": str(row.get("input", "")),
            "turn": row.get("turn"),
            "expected_behaviour": str(row.get("expected_behaviour", "")),
            "expected_tools": [str(tool) for tool in row.get("expected_tools", [])],
        }
        for row in _rows(folder / TURN_DATASET)
    ]


def call_goldens(folder: Path) -> list[dict[str, Any]]:
    """The ring-2 goldens of a project: who calls, what they want, and what must hold."""
    return [
        {
            "name": str(row.get("name", "")),
            "persona": str(row.get("persona", "")),
            "objective": str(row.get("objective", "")),
            "turns": [str(turn) for turn in row.get("turns", [])],
            "policies": [str(policy) for policy in row.get("policies", [])],
            "max_turns": row.get("max_turns"),
        }
        for row in _rows(folder / CALL_DATASET)
    ]


def _suite(folder: Path, name: str, target: str) -> dict[str, Any]:
    """One declared suite, with whichever dataset its pytest target says it reads."""
    source = _read(REPO_ROOT / target)
    if CALL_DATASET in source:
        return _view(name, target, CALL_DATASET, "call", call_goldens(folder))
    if TURN_DATASET in source:
        return _view(name, target, TURN_DATASET, "turn", turn_goldens(folder))
    return {
        "suite": name,
        "target": target,
        "dataset": None,
        "kind": "code",
        "count": None,
        "goldens": [],
    }


def _ring2(folder: Path) -> list[dict[str, Any]]:
    """The suite declared by convention rather than by `suites.json`, when the project has one."""
    if not (folder / RING2_TARGET).is_file():
        return []
    target = str((folder / RING2_TARGET).relative_to(REPO_ROOT))
    return [_view(RING2_SUITE, target, CALL_DATASET, "call", call_goldens(folder))]


def _view(
    name: str, target: str, dataset: str, kind: str, goldens: list[dict[str, Any]]
) -> dict[str, Any]:
    """One suite as the console draws it: what it runs, what it reads, and how many cases."""
    return {
        "suite": name,
        "target": target,
        "dataset": dataset,
        "kind": kind,
        "count": len(goldens),
        "goldens": goldens,
    }


def _evals_dir(tenant: str, project: str) -> Path | None:
    """Where this project's evals live, or None when the ids name nothing on disk."""
    if not (SAFE_ID.match(tenant) and SAFE_ID.match(project)):
        return None
    folder = TENANTS_DIR / tenant / "projects" / project / "evals"
    return folder if folder.is_dir() else None


def _rows(path: Path) -> list[dict[str, Any]]:
    """A dataset file as a list of objects; an absent or malformed file is simply empty."""
    try:
        found = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [row for row in found if isinstance(row, dict)] if isinstance(found, list) else []


def _read(path: Path) -> str:
    """The text of a pytest target, so the dataset it names can be seen without importing it."""
    try:
        return path.read_text()
    except OSError:
        return ""
