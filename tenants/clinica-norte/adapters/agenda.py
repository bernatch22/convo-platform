"""FakeAgenda: Clínica Norte's appointment book, invented but never random.

It stands where the clinic's real booking system will stand and answers the same
shape: a capability name, a dict of arguments, a plain result. Reading is
`find_availability` and `find_patient`; writing is `cancel_slot`, `book_slot`,
`create_appointment` and `rebook_slot`, the inverse of the cancel that the saga
runs when a booking falls over halfway.

`book_slot` and `create_appointment` write the same row and are deliberately two
capabilities. One takes an hour for a patient the book already holds — a
rescheduling, released hour and all — and the other opens a record for somebody
who had nothing. A real agenda distinguishes them (the second one creates the
patient), the catalog gives them separate specs, and the consent metric watches
one name each: a single capability would leave "which write ran?" a question
about arguments rather than about a name in a list.

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
import time
from typing import Any

from core.adapters.base import CHANGED, GONE, LIST_RECORDS, NEW, PLAIN, Adapter
from core.adapters.ledger import Ledger

from . import patients, slots
from .slots import DOCTORS, normalise, specialty_key  # re-exported: the cuadro médico lives there

LEDGER_BOOK = "clinica-norte/agenda"

# How the book itself describes a row to whoever is reading the console. These are
# the clinic's words about its own records, not the platform's: `moved` is one
# appointment the patient rescheduled, which the platform only ever saw as a cancel
# followed by a booking.
BOOKED = "booked"
CREATED = "created"
MOVED = "moved"
CANCELLED = "cancelled"

SHAPE = "appointments"
LABELS = {
    "who": "patient",
    "contact": "phone",
    "when": "appointment",
    "handled_by": "professional",
    "detail": "specialty",
}

FIND_AVAILABILITY = "find_availability"
FIND_PATIENT = "find_patient"
BOOK_SLOT = "book_slot"
CREATE_APPOINTMENT = "create_appointment"
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

    def __init__(self, seed: str = "clinica-norte", ledger: Ledger | None = None) -> None:
        self.seed = seed
        self.book = patients.seeded()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.ledger = ledger or Ledger(LEDGER_BOOK)
        self.released = False  # this call has already let an hour go: the next write is a move

    def capabilities(self) -> list[str]:
        """Everything the booking system can be asked to do, read and write alike."""
        return [
            FIND_AVAILABILITY,
            FIND_PATIENT,
            BOOK_SLOT,
            CREATE_APPOINTMENT,
            CANCEL_SLOT,
            REBOOK_SLOT,
            LIST_RECORDS,
        ]

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        """Run one capability against the book; ValueError on anything it cannot read."""
        self.calls.append((capability, args))
        runner = {
            FIND_AVAILABILITY: self._find_availability,
            FIND_PATIENT: self._find_patient,
            BOOK_SLOT: self._book_slot,
            CREATE_APPOINTMENT: self._create_appointment,
            CANCEL_SLOT: self._cancel_slot,
            REBOOK_SLOT: self._rebook_slot,
            LIST_RECORDS: self._list_records,
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
        return self._write(args)

    def _create_appointment(self, args: dict[str, Any]) -> dict[str, str]:
        """Open a cita for somebody the book did not hold; 13:00 is refused here too.

        A new patient needs a name and a number — the row is the only record of
        them and the SMS has nowhere else to go — so an empty one is a
        `ValueError` rather than a nameless appointment nobody can find again.
        The refused hour behaves exactly as it does for a rescheduling: the
        clinic's system says no at 13:00 whichever door you knock at, and the
        saga above compensates the same way.
        """
        if not str(args.get("patient", "")).strip() or not str(args.get("phone", "")).strip():
            raise ValueError("create_appointment needs the patient's name and phone")
        return self._write(args, specialty=str(args.get("specialty", "")).strip())

    def _write(self, args: dict[str, Any], specialty: str = "") -> dict[str, str]:
        """The row both writes leave behind: an id built from the slot, and the hour it holds."""
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
            **({"specialty": specialty} if specialty else {}),
        }
        moved = self.released  # an hour was let go earlier in this call: this is a rescheduling
        self._file(appointment_id, MOVED if moved else CREATED, CHANGED if moved else NEW)
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
        gone = status == "cancelled"
        self.released = self.released or gone
        self._file(appointment_id, CANCELLED if gone else BOOKED, GONE if gone else PLAIN)
        return {"appointment_id": appointment_id, "status": status}

    def _list_records(self, _args: dict[str, Any]) -> dict[str, Any]:
        """The appointment book as an operator reads it: every cita, and how each one stands.

        The console's read, never a tool: no stage may call it and no model ever
        sees it. It answers with the clinic's own shape and the clinic's own
        words for a state, so `core` renders a table it has no vocabulary for.

        Two sources, in this order. The seeded book is what the clinic held
        before anyone rang; the ledger is every row a call has written since,
        across every process, and it wins wherever both hold the same id — a
        cita cancelled at eleven is cancelled, whatever the seed still says.
        """
        rows = {key: self._as_record(key, row) for key, row in self.book.items()}
        rows.update(self.ledger.rows())
        return {"shape": SHAPE, "labels": LABELS, "rows": list(rows.values())}

    def _file(self, appointment_id: str, state: str, tone: str) -> None:
        """Record the row's new standing where another process reads it (`core.adapters.ledger`)."""
        row = self.book.get(appointment_id)
        if row is not None:
            self.ledger.record(appointment_id, self._as_record(appointment_id, row, state, tone))

    def _as_record(
        self, appointment_id: str, row: dict[str, str], state: str = "", tone: str = ""
    ) -> dict[str, Any]:
        """One appointment in the shape the console reads (`core.adapters.base.LIST_RECORDS`)."""
        return {
            "id": appointment_id,
            "who": row.get("patient", ""),
            "contact": row.get("phone") or None,
            "when": row.get("when") or None,
            "handled_by": row.get("doctor") or None,
            "state": state or (CANCELLED if row.get("status") == "cancelled" else BOOKED),
            "tone": tone or (GONE if row.get("status") == "cancelled" else PLAIN),
            "detail": row.get("specialty") or None,
            "at": time.time() if state else None,
        }


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
