"""What this project's agent can be wrong about, and what its calls may know.

Decisions: docs/decisions/tenants._template.projects.example.evals.grounding.md
"""

import re

from convo.testing.metrics import grounding

from ..project import PROJECT

REFERENCE = "reserva"
PRICE = "precio"
HOUR = "hora"
PHONE = "teléfono"

# `EX-1001`, `EX 1001`, `ex1001` — however it is read out, it is one booking.
BOOKING_REFERENCE = re.compile(r"\bEX[\s\-]?\d{3,6}\b", re.IGNORECASE)

# The reference is checked against the CALL and not against the knowledge sheet: which
# booking THIS call is about is something only the customer or the system said.
EXTRACTORS = (
    grounding.vocabulary(REFERENCE, BOOKING_REFERENCE, grounding.CALL),
    grounding.prices(PRICE),
    grounding.clock_hours(HOUR),
    grounding.phones(PHONE),
)


def stated_data(turns: list) -> list[grounding.Datum]:
    """Every reference, price, hour and phone number the agent stated."""
    return grounding.stated_data(turns, EXTRACTORS)


def evidence_of(turns: list) -> grounding.Evidence:
    """The business's sheet, what the customer said, and every tool output of the call."""
    return grounding.evidence_of(turns, PROJECT.knowledge_seed)
