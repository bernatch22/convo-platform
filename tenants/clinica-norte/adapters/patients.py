"""The appointments Clínica Norte already has on the book, as a seeded demo map.

A rescheduling call starts from an appointment that exists, so the fake agenda
has to know a handful of patients before anyone picks up the phone. Real
systems look this up by phone number and confirm with a name; so does `lookup`,
and it accepts either — a caller who reads their number out and a caller who
only gives a name both get identified, which is what happens on a real line.

Never real data: the names are invented and the phone numbers are in the
Spanish 600-block reserved for fiction. A customer replaces this module with
their CRM and keeps `lookup`'s two arguments and its return shape.
"""

import datetime

from .slots import normalise

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
    """The appointment of the patient identified by phone or by name, or None if there is none.

    The phone wins when both are given: two patients can share a name and a
    misheard surname is the commonest error on a phone line, while a number the
    caller reads out digit by digit is the strongest identifier we get.
    """
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


def as_of(appointment: dict[str, str]) -> datetime.datetime:
    """The moment an appointment is set for, as a datetime the project can format."""
    return datetime.datetime.fromisoformat(appointment["when"])


def _digits(phone: str | None) -> str:
    return "".join(c for c in phone if c.isdigit()) if isinstance(phone, str) else ""


def _same_person(said: str, stored: str) -> bool:
    """A name matches when every word the caller said appears in the stored name.

    Patients give a first name and one surname where the book holds two, so an
    exact comparison would fail almost every real call.
    """
    words = normalise(said).split()
    known = normalise(stored).split()
    return bool(words) and all(word in known for word in words)
