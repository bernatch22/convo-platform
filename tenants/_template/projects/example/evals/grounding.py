"""What this project's agent can be wrong about, and what its calls may know.

The machinery — extract, match, escalate the remainder — is
`core.testing.grounding`, shared by every tenant. What lives here is the
vocabulary: the kinds of claim a customer would ACT on and an agent could
invent. Clock hours, prices and phone numbers come free from core.

TODO(copy): one extractor per thing of yours that has a canonical form — an
order number, a policy number, a carrier, a professional's name. A claim no
extractor knows is never checked, so this list is the ceiling of the grounding
metric.

Two functions are the whole contract with the platform: `stated_data(turns)`
and `evidence_of(turns)`.
"""

import re

from convo.testing.metrics import grounding

from ..knowledge import BUSINESS

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
    return grounding.evidence_of(turns, BUSINESS)
