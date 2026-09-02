"""The appointments Clínica Norte already has on the book, as a seeded demo map.

Decisions: docs/decisions/tenants.clinica-norte.adapters.patients.md
"""

import datetime

from .slots import normalise

SPOKEN_DIGITS = 3  # how much of a number reception may say out loud to validate it
PHONE_DIGITS = 9  # a Spanish number: anything shorter is a misheard one, not a new one

# appointment_id -> the appointment as the booking system holds it today.
APPOINTMENTS: dict[str, dict[str, str]] = {
    "ap-20260903-1000-trau": {
        "patient": "Ana García Ruiz",
        "phone": "600123456",
        "when": "2026-09-03T10:00",
        "doctor": "Dra. Irene Campos",
        "specialty": "traumatología",
    },
    "ap-20260904-0930-pedi": {
        "patient": "Luis Ortega Marín",
        "phone": "600987654",
        "when": "2026-09-04T09:30",
        "doctor": "Dr. Pablo Iglesias",
        "specialty": "pediatría",
    },
    "ap-20260908-1730-derm": {
        "patient": "Carmen Vidal Soto",
        "phone": "600555111",
        "when": "2026-09-08T17:30",
        "doctor": "Dra. Sofía Lombardo",
        "specialty": "dermatología",
    },
}


def seeded() -> dict[str, dict[str, str]]:
    """A fresh copy of the demo book: one adapter per session must not share state."""
    return {key: dict(value) for key, value in APPOINTMENTS.items()}


def lookup(
    book: dict[str, dict[str, str]], name: str | None, phone: str | None
) -> dict[str, str] | None:
    """The appointment of the patient identified by phone or by name, or None if there is none."""
    digits = _digits(phone)
    for identifier, appointment in book.items():
        if appointment.get("status") == "cancelled":
            continue
        if digits and _digits(appointment["phone"]) == digits:
            return {"appointment_id": identifier, **appointment}
    for identifier, appointment in book.items():
        if appointment.get("status") == "cancelled":
            continue
        if name and _same_person(name, appointment["patient"]):
            return {"appointment_id": identifier, **appointment}
    return None


def update_phone(
    book: dict[str, dict[str, str]], appointment_id: str, phone: str
) -> dict[str, str]:
    """Write a new contact number onto the patient's record; ValueError if there is none."""
    record = book.get(appointment_id)
    if record is None:
        raise ValueError(f"unknown appointment {appointment_id!r}")
    digits = _digits(phone)
    if len(digits) < PHONE_DIGITS:
        raise ValueError(f"{phone!r} is not a phone number the clinic can call")
    # Read before writing: the record being changed is itself in the loop below, and
    # comparing against a field the loop has already overwritten matches only the row
    # that happened to come first.
    previous = _digits(record["phone"])
    for appointment in book.values():
        if _digits(appointment["phone"]) == previous:
            appointment["phone"] = digits
    return {"appointment_id": appointment_id, "phone": digits}


def last_digits(phone: str | None) -> str:
    """The tail of a number, and the only part of it anybody reads back out loud."""
    return _digits(phone)[-SPOKEN_DIGITS:]


def as_of(appointment: dict[str, str]) -> datetime.datetime:
    """The moment an appointment is set for, as a datetime the project can format."""
    return datetime.datetime.fromisoformat(appointment["when"])


def _digits(phone: str | None) -> str:
    return "".join(c for c in phone if c.isdigit()) if isinstance(phone, str) else ""


def _same_person(said: str, stored: str) -> bool:
    """A name matches when every word the caller said appears in the stored name."""
    words = normalise(said).split()
    known = normalise(stored).split()
    return bool(words) and all(word in known for word in words)
