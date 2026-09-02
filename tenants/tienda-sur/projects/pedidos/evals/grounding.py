"""What Tienda Sur's order desk can be wrong about, and what its calls may know.

Decisions: docs/decisions/tenants.tienda-sur.projects.pedidos.evals.grounding.md
"""

import re

from convo.testing.metrics import grounding

from ..project import PROJECT

ORDER = "pedido"
TICKET = "incidencia"
TRACKING = "seguimiento"
CARRIER = "transportista"
PRICE = "precio"
HOUR = "hora"
PHONE = "teléfono"

# `TS-10432`, `TS 10432`, `ts10432` — however it is read out, it is one order.
ORDER_NUMBER = re.compile(r"\bTS[\s\-]?\d{4,6}\b", re.IGNORECASE)
# `TS-T0003`, `TS T0003`, `tst0003` — an incident number, which is not an order number: the
# shop mints it mid-call, so a wrong one sends the customer back to a ticket that is not
# theirs, or to none at all.
TICKET_NUMBER = re.compile(r"\bTS[\s\-]?T[\s\-]?\d{3,5}\b", re.IGNORECASE)
# A Spanish parcel reference: two letters, nine digits, the country code.
TRACKING_CODE = re.compile(r"\b[A-Z]{2}\d{9}ES\b")
# The carriers the shop actually works with. A name outside this list is not a claim we
# can check — it is a claim about a company we do not use, which the judge will read.
CARRIER_NAME = re.compile(r"\b(?:Correos Express|Correos|SEUR|MRW|GLS)\b", re.IGNORECASE)

# The carrier is checked against the CALL and not against the sheet on purpose: the sheet
# names every carrier the shop works with, so it would ground "lo lleva MRW" about a parcel
# SEUR is carrying. Which company has THIS parcel is something only the order system said.
EXTRACTORS = (
    grounding.vocabulary(ORDER, ORDER_NUMBER, grounding.CALL),
    grounding.vocabulary(TICKET, TICKET_NUMBER, grounding.CALL),
    grounding.vocabulary(TRACKING, TRACKING_CODE, grounding.CALL),
    grounding.vocabulary(CARRIER, CARRIER_NAME, grounding.CALL),
    grounding.prices(PRICE),
    grounding.clock_hours(HOUR),
    grounding.phones(PHONE),
)


def stated_data(turns: list) -> list[grounding.Datum]:
    """Every order and incident number, tracking code, carrier, price, hour and phone stated."""
    return grounding.stated_data(turns, EXTRACTORS)


def evidence_of(turns: list) -> grounding.Evidence:
    """The shop's sheet, what the customer said, and every tool output of the call."""
    return grounding.evidence_of(turns, PROJECT.knowledge_seed)


def unsupported(data: list[grounding.Datum], evidence: grounding.Evidence):
    """The data no source in the call accounts for — what is worth asking a judge about."""
    return grounding.unsupported(data, evidence)
