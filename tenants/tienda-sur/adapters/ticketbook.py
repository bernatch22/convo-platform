"""The incidents Tienda Sur already has open, as a seeded demo book.

An order exists before anyone rings; a ticket does not. That single difference
is why this module has one function the order book never needed — `mint`, which
hands out the next free number — and why the ids it mints look the way they do:
`TS-T0007` is read out loud over the phone, digit by digit, so it is short, it
carries the shop's own prefix, and it can never be mistaken for an order.

Never real data: the names are invented and the phone numbers are in the
Spanish 600-block reserved for fiction. A customer replaces this module with
their own helpdesk API and keeps `lookup`, `mint` and the row shape.
"""

import re

OPEN = "abierto"
IN_PROGRESS = "en curso"
RESOLVED = "resuelto"

TEAM = "Atención al cliente"

# `TS-T0001` however it is read out: "te ese te cero cero cero uno", "ts t 1", "TST0001".
READING = re.compile(r"TST0*(\d{1,4})")

# ticket number -> the incident as the shop's helpdesk holds it today.
TICKETS: dict[str, dict[str, str]] = {
    "TS-T0001": {
        "name": "Javier Nieto Salas",
        "phone": "600444555",
        "subject": "el paquete aparece como entregado pero no lo ha recibido nadie en casa",
        "status": IN_PROGRESS,
        "opened": "2026-08-26",
        "team": TEAM,
        "order_id": "TS-10433",
    },
    "TS-T0002": {
        "name": "Lucía Ferrer Blanco",
        "phone": "600666777",
        "subject": "las zapatillas llegaron con una marca en la puntera",
        "status": RESOLVED,
        "opened": "2026-08-21",
        "team": TEAM,
        "order_id": "TS-10434",
    },
}

# What a caller may dictate into a ticket. Long enough for the whole complaint in one
# breath, short enough that nothing can paste a database into the shop's helpdesk.
SUBJECT_CHARS = 300

STATUS_NOTES = {
    OPEN: "recién abierta, todavía nadie la ha cogido",
    IN_PROGRESS: "un compañero la está mirando",
    RESOLVED: "ya está resuelta y cerrada",
}


def seeded() -> dict[str, dict[str, str]]:
    """A fresh copy of the demo book: one adapter per session must not share state."""
    return {key: dict(value) for key, value in TICKETS.items()}


def lookup(
    book: dict[str, dict[str, str]], number: str | None, phone: str | None
) -> dict[str, str] | None:
    """The incident identified by its number or by the phone that opened it, or None.

    The number wins when both are given: it identifies one incident, while a
    phone identifies a customer who may have several — and when only a phone
    arrives, the most recent one is the one they are calling about.
    """
    found = book.get(normalise(number))
    if found is not None:
        return {"ticket_id": normalise(number), **found}
    digits = _digits(phone)
    theirs = [
        {"ticket_id": key, **ticket}
        for key, ticket in book.items()
        if digits and _digits(ticket.get("phone")) == digits
    ]
    return max(theirs, key=lambda ticket: ticket["opened"]) if theirs else None


def mint(book: dict[str, dict[str, str]]) -> str:
    """The next free ticket number, one past the highest the book already holds.

    Sequential and not random on purpose: the number is dictated over the phone
    and typed back in by hand on the next call, so four digits a person can read
    without spelling beats an opaque id nobody can repeat. The book it counts
    over is the merged one — seed plus ledger — so a second process picks up
    where the first left off instead of minting a number that already exists.
    """
    taken = [int(match.group(1)) for key in book if (match := READING.fullmatch(_flat(key)))]
    return f"TS-T{max(taken, default=0) + 1:04d}"


def normalise(number: str | None) -> str:
    """`TS-T0001`, `ts t 1`, `TST0001` — one shape, because it is read out loud."""
    if not isinstance(number, str):
        return ""
    match = READING.fullmatch(_flat(number))
    return f"TS-T{int(match.group(1)):04d}" if match else ""


def subject_of(text: str | None) -> str:
    """The customer's own words, trimmed to what a helpdesk field holds; never rewritten."""
    return " ".join(str(text or "").split())[:SUBJECT_CHARS]


def _flat(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _digits(text: str | None) -> str:
    return "".join(c for c in text if c.isdigit()) if isinstance(text, str) else ""
