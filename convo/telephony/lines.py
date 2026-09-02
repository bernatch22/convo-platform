"""The phone line as data: which number reaches which project, and how to say it.

Decisions: docs/decisions/convo.telephony.lines.md
"""

import json
from typing import Any

from convo import settings
from convo.api.auth import fleet
from convo.state.store import Route, Store

# User-facing, and Spanish because the operator of this console is: a project
# nobody can call is the one fact the pipeline screen must not soften.
NO_LINE = "sin número asignado — las llamadas entrantes no llegan a este proyecto"


def seeded_lines() -> list[Route]:
    """The lines this deployment is known to answer, read from `infra/seed/routes.json`."""
    path = settings.seed_routes_file()
    if not path.exists():
        return []
    return [Route(**row) for row in json.loads(path.read_text())]


def seed(store: Store) -> list[Route]:
    """Put this deployment's known lines into a store that does not have them yet."""
    written = [line for line in seeded_lines() if store.route(line.fleet, line.key) is None]
    for line in written:
        store.add_route(line)
    return written


def view(store: Store, tenant: str, project: str) -> dict[str, Any]:
    """Every phone line that reaches one project, or the sentence that says there is none."""
    serving = fleet()
    lines = [
        {
            "number": route.key,
            "fleet": route.fleet,
            "channel": route.channel,
            "serving": route.fleet == serving,
        }
        for route in store.routes()
        if (route.tenant, route.project) == (tenant, project)
    ]
    return {"fleet": serving, "lines": lines, "note": _note(lines, serving)}


def _note(lines: list[dict[str, Any]], serving: str) -> str:
    """What the screen says under the numbers — including when there are none."""
    if not lines:
        return NO_LINE
    if not any(line["serving"] for line in lines):
        others = ", ".join(sorted({str(line["fleet"]) for line in lines}))
        return (
            f"registered on fleet {others} — this deploy dispatches to {serving!r}, so calls to "
            "these numbers never reach this process. Move the route or the FLEET of this deploy."
        )
    return (
        f"the SIP dispatch rule hands an inbound call to the {serving!r} fleet and "
        "the router reads this row to decide whose project answers it. Changing it is a "
        "change to the dispatch rule on the box, not a setting on this screen."
    )
