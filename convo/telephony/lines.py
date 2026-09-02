"""The phone line as data: which number reaches which project, and how to say it.

A number is not a field of a project. It is a ROUTE — one row keyed by fleet
and dialled number, the same `routes` table `core/router.py` reads when a call
arrives — so a project has zero, one or several lines, and the console has to
be able to say all three honestly. That is the whole reason this module exists:
before it, the number lived as a string in the web client's chrome, printed
under every tenant, which made two projects look like they shared a line when
only one of them was reachable by phone at all.

The store is where the mapping lives; the SIP dispatch rule on the box is what
actually routes the call. `SEEDED_LINES` is that rule written down so a fresh
database is not empty and honest-looking at the same time, and `seed` only ever
FILLS A GAP: a key already in the store is left exactly as the operator set it,
because the operator has seen the box more recently than this file has.

Nothing here assigns or buys a number. Assigning one means editing the
livekit-sip dispatch rule over the LiveKit API; buying one means a Twilio
purchase, which we do not automate — carrier automation is indistinguishable
from an account takeover, and it is the fastest way to lose a trunk.
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
    """Put this deployment's known lines into a store that does not have them yet.

    Returns only what it actually wrote, so a caller can log a first run and
    stay silent on every one after it. A key already present is never touched.
    """
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
    """What the screen says under the numbers — including when there are none.

    Three different truths, and a project owner reads them differently: no line
    at all (the phone door is shut), a line this deploy answers, or a line
    registered against another fleet, which is worse than none — the number
    exists, somebody may be handing it out, and no call on it ever reaches this
    process.
    """
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
