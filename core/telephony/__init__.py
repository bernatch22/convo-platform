"""The phone as a destination, not just an origin: moving a live call to a human.

`transfer` holds the two LiveKit SIP moves — a cold REFER that hands the
caller's leg to the carrier, and a warm leg that dials a human INTO the room —
and `isolation` holds the one primitive the warm path needs and the SFU is the
only thing that can provide: making one participant inaudible to another
without their client's cooperation. `handover` is the choreography: what the
caller hears, what the human hears, and what the log ends up saying.

Nothing here imports `tenants/`, and nothing here decides WHO may transfer:
that gate is `core.security.control.SupervisorControl.apply`, one door for
every supervision verb.
"""

from core.telephony.transfer import (
    COLD,
    MODES,
    WARM,
    Outcome,
    TransferRefused,
    WarmLeg,
    cold,
    dial_uri,
    phone_number,
)

__all__ = [
    "COLD",
    "MODES",
    "WARM",
    "Outcome",
    "TransferRefused",
    "WarmLeg",
    "cold",
    "dial_uri",
    "phone_number",
]
