"""FakeAgenda: Clínica Norte's appointment book, invented but never random.

It stands where the clinic's real booking system will stand and answers the same
shape: a capability name, a dict of arguments, a plain result. Reading is
`find_availability` and `find_patient`; writing is `cancel_slot`, `book_slot`
and `rebook_slot`, the inverse of the cancel that the saga runs when a booking
falls over halfway.

One failure is deliberate and deterministic: a slot at 13:00 (`-1300-` in its
id) is always rejected. It is the demo's "the customer's system said no" case,
and it exists so the compensated path can be reproduced on demand instead of
waited for.

Open source note: this file is the template a customer copies. Replace each
method with an HTTP call to your own agenda, keep `capabilities()` and the
result shapes, and every layer above (tool, guard, saga, executor, prompt)
works unchanged. An argument the system cannot read raises `ValueError`, which
the executor turns into a sentence the caller hears — never a stack trace.
"""

import datetime
import re
from typing import Any

from core.adapters.base import Adapter

from . import patients, slots
from .slots import DOCTORS, normalise, specialty_key  # re-exported: the cuadro médico lives there

FIND_AVAILABILITY = "find_availability"
FIND_PATIENT = "find_patient"
BOOK_SLOT = "book_slot"
CANCEL_SLOT = "cancel_slot"
REBOOK_SLOT = "rebook_slot"

REJECTED_HOUR = "-1300-"  # the demo's deterministic failure: the system refuses 13:00
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

NO_SLOTS = "no free slots that day"
NO_PATIENT = "no appointment on the book for that caller"
NOTHING_WRITTEN = "the booking system returned nothing"

__all__ = [
    "DOCTORS",
    "FakeAgenda",
    "normalise",
    "specialty_key",
    "summarise_availability",
    "summarise_change",
    "summarise_patient",
]


class FakeAgenda(Adapter):
    """The clinic's appointment book: which hours are free, who has a cita, and booking them."""

    def __init__(self, seed: str = "clinica-norte") -> None:
        self.seed = seed
        self.book = patients.seeded()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def capabilities(self) -> list[str]:
        """Everything the booking system can be asked to do, read and write alike."""
        return [FIND_AVAILABILITY, FIND_PATIENT, BOOK_SLOT, CANCEL_SLOT, REBOOK_SLOT]

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        """Run one capability against the book; ValueError on anything it cannot read."""
        self.calls.append((capability, args))
        runner = {
            FIND_AVAILABILITY: self._find_availability,
            FIND_PATIENT: self._find_patient,
            BOOK_SLOT: self._book_slot,
            CANCEL_SLOT: self._cancel_slot,
            REBOOK_SLOT: self._rebook_slot,
        }.get(capability)
        if runner is None:
            raise ValueError(f"FakeAgenda cannot run {capability!r}")
        return runner(args)

    def find_availability(self, day: Any, specialty: Any = None) -> list[dict[str, str]]:
        """Up to three free slots on `day` (YYYY-MM-DD), for a specialty when one is named.

        A closed day (Sunday) legitimately has none: an empty list is an answer,
        not a failure, and the receptionist says so and offers another day.
        """
        return slots.free_slots(self.seed, _parse_day(day), specialty)

    def booked(self) -> list[dict[str, str]]:
        """Every appointment this session created, in the order it created them."""
        return [a for a in self.book.values() if a.get("created") == "session"]

    def _find_availability(self, args: dict[str, Any]) -> list[dict[str, str]]:
        return self.find_availability(args.get("date"), args.get("specialty"))

    def _find_patient(self, args: dict[str, Any]) -> dict[str, str] | None:
        return patients.lookup(self.book, args.get("name"), args.get("phone"))

    def _book_slot(self, args: dict[str, Any]) -> dict[str, str]:
        """Take a free slot for a patient; a 13:00 slot is always refused (module docstring)."""
        identifier = str(args.get("slot_id", ""))
        when = slots.moment_of(identifier)
        if REJECTED_HOUR in identifier:
            raise ValueError(f"the booking system refused slot {identifier}")
        appointment_id = f"ap-{identifier.removeprefix('sl-')}"
        self.book[appointment_id] = {
            "patient": str(args.get("patient", "")),
            "phone": str(args.get("phone", "")),
            "when": when,
            "doctor": str(args.get("doctor", "")),
            "created": "session",
        }
        return {"appointment_id": appointment_id, "when": when}

    def _cancel_slot(self, args: dict[str, Any]) -> dict[str, str]:
        return self._set_status(args, "cancelled")

    def _rebook_slot(self, args: dict[str, Any]) -> dict[str, str]:
        """Undo a cancel: the appointment the saga released goes back on the book as it was."""
        return self._set_status(args, "booked")

    def _set_status(self, args: dict[str, Any], status: str) -> dict[str, str]:
        appointment_id = str(args.get("appointment_id", ""))
        appointment = self.book.get(appointment_id)
        if appointment is None:
            raise ValueError(f"unknown appointment {appointment_id!r}")
        appointment["status"] = status
        return {"appointment_id": appointment_id, "status": status}


def summarise_availability(slots: list[dict[str, str]] | None) -> str:
    """What `find_availability` may leave in the session log: the hours and who consults them.

    Every field of a slot is clinic data — an ISO moment, a professional, an
    opaque id — and none of it identifies the person on the phone, so the rows
    can be kept whole. That is what lets a replayed call prove an hour the
    receptionist read out came off the agenda instead of out of the model.
    """
    if not slots:
        return NO_SLOTS
    return f"{len(slots)} free slots: " + "; ".join(
        f"{slot.get('when', '?')} {slot.get('doctor', '?')}" for slot in slots
    )


def summarise_patient(appointment: dict[str, str] | None) -> str:
    """What `find_patient` may leave in the log: when, with whom, and a name the mask blanks.

    The appointment the caller already has is the fact a replayed call could
    never ground — reception reads it back in the first minute of every
    rescheduling call — and it is also the one result here that carries a
    person. The name is rendered anyway and the executor masks it, so the log
    ends up holding `An*************`: enough for an auditor to see that
    somebody was found and which of two callers it was, and nothing more. The
    phone is simply not rendered; a masked number would say the same thing
    twice.
    """
    if not appointment:
        return NO_PATIENT
    return (
        f"appointment {appointment.get('appointment_id', '?')} "
        f"for {appointment.get('patient', '?')} "
        f"on {appointment.get('when', '?')} with {appointment.get('doctor', '?')}"
    )


def summarise_change(change: dict[str, str] | None) -> str:
    """What a write did to the book: the appointment it touched, and how it now stands.

    `book_slot`, `cancel_slot` and `rebook_slot` all answer with an appointment
    id and one more field — the moment it now holds, or the status it now has —
    so one renderer covers the three and a saga's undo reads in the log as
    plainly as the write it undid. Nothing here names a person: the patient and
    the phone were arguments, and the log already carries them masked.
    """
    if not change:
        return NOTHING_WRITTEN
    identifier = change.get("appointment_id", "?")
    standing = change.get("when") or change.get("status") or "?"
    return f"appointment {identifier} now {standing}"


def _parse_day(value: Any) -> datetime.date:
    """The day as a date, or ValueError — the executor turns that into a spoken sentence."""
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value.strip()):
        raise ValueError(f"find_availability needs a date as YYYY-MM-DD, got {value!r}")
    return datetime.date.fromisoformat(value.strip())
