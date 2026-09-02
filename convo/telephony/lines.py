"""The phone line as data: which number reaches which project, and how to say it.

Decisions: docs/decisions/convo.telephony.lines.md
"""

from typing import Any

from convo.api.auth import fleet
from convo.state.store import Route, Store

# The livekit-sip dispatch rule as it stands today, written down: one Twilio
# number on the `cc` fleet, answering as Clínica Norte's reagendamiento. Adding
# a line here does NOT create it — it only stops a fresh store from disagreeing
# with the box. tienda-sur is deliberately absent: it has no number.
SEEDED_LINES = (Route("cc", "+14176743169", "clinica-norte", "reagendamiento", "voice"),)

# User-facing, and Spanish because the operator of this console is: a project
# nobody can call is the one fact the pipeline screen must not soften.
NO_LINE = "sin número asignado — las llamadas entrantes no llegan a este proyecto"


def seed(store: Store) -> list[Route]:
    """Put this deployment's known lines into a store that does not have them yet."""
    written = [line for line in SEEDED_LINES if store.route(line.fleet, line.key) is None]
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
        "core/router.py reads this row to decide whose project answers it. Changing it is a "
        "change to the dispatch rule on the box, not a setting on this screen."
    )
