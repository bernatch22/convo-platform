"""The appointments Clínica Norte already has on the book, as a seeded demo map.

A rescheduling call starts from an appointment that exists, so the fake agenda
has to know a handful of patients before anyone picks up the phone. Real
systems look this up by phone number and confirm with a name; so does `lookup`,
and it accepts either — a caller who reads their number out and a caller who
only gives a name both get identified, which is what happens on a real line.

Since ms-20 the book is also written to. `update_phone` is the setter behind
the clinic's third irreversible verb: the number the clinic calls a patient on
is data the patient owns, and a caller who has been identified may change it.
It moves every appointment of the same person at once, because a number belongs
to a person and not to a row.

Never real data: the names are invented and the phone numbers are in the
Spanish 600-block reserved for fiction. A customer replaces this module with
their CRM and keeps `lookup`'s two arguments and its return shape.
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


def update_phone(
    book: dict[str, dict[str, str]], appointment_id: str, phone: str
) -> dict[str, str]:
    """Write a new contact number onto the patient's record; ValueError if there is none.

    Every appointment of the same patient moves together. A phone number is a
    property of the person, not of one row, and a clinic that changed the number
    on the cita the caller happened to mention would still ring the old one for
    the next appointment — which is the failure this verb exists to fix.

    The refusal is the point of the `ValueError`: an id the book does not hold
    is a caller nobody identified, and the platform must not invent a record to
    write into.
    """
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
    """The tail of a number, and the only part of it anybody reads back out loud.

    A Spanish caller validates a number on file the way a bank does it — «acaba
    en 456» — and that idiom is a data-protection rule with a voice: the person
    who really owns the number recognises three digits, and somebody guessing
    learns nothing worth having. It lives here, next to the records, because the
    prompt that speaks it and the log line that stores it must not drift into two
    different idioms.
    """
    return _digits(phone)[-SPOKEN_DIGITS:]


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
