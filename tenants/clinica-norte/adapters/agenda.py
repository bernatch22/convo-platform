"""FakeAgenda: Clínica Norte's appointment book, invented but never random.

Decisions: docs/decisions/tenants.clinica-norte.adapters.agenda.md
"""

import datetime
import re
import time
from typing import Any

from convo.adapters.base import CHANGED, GONE, LIST_RECORDS, NEW, PLAIN, Adapter
from convo.adapters.ledger import Ledger

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
CONFIRMED = "confirmed"
RECONTACTED = "phone updated"

# How the book stores a row's standing, and how the console should draw it. The
# clinic owns both halves: `tone` is the only presentational field in the console's
# contract and it is deliberately the business that decides a cancelled cita is gone
# (`core.adapters.base`). A status this map does not know reads as a plain booking.
STATES: dict[str, tuple[str, str]] = {
    "cancelled": (CANCELLED, GONE),
    "confirmed": (CONFIRMED, CHANGED),
    "booked": (BOOKED, PLAIN),
}

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
CANCEL_APPOINTMENT = "cancel_appointment"
CONFIRM_ATTENDANCE = "confirm_attendance"
REBOOK_SLOT = "rebook_slot"
UPDATE_CONTACT = "update_contact"

REJECTED_HOUR = "-1300-"  # the demo's deterministic failure: the system refuses 13:00
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

NO_SLOTS = "no free slots that day"
NO_PATIENT = "no appointment on the book for that caller"
NOTHING_WRITTEN = "the booking system returned nothing"
NO_CONTACT = "the booking system changed no contact detail"

__all__ = [
    "DOCTORS",
    "FakeAgenda",
    "normalise",
    "specialty_key",
    "summarise_availability",
    "summarise_change",
    "summarise_contact",
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
        # Hours a cancellation gave back, by slot id. A cancelled cita is not just a row
        # with a word on it: it is half an hour of a professional's day that the next
        # caller may have, and an agenda that kept offering the same three seeded hours
        # after a cancel would be telling the patient their hour was released and the
        # next caller that it never existed.
        #
        # In memory, and therefore for this session only — the same seam as `self.book`,
        # and for the same reason: the ledger is write-through and never read back into a
        # conversation, so no test can be contaminated by what another one cancelled. A
        # real agenda is one system every process reaches and has no such seam; what the
        # fake has to reproduce is the BEHAVIOUR a call can observe, which it does.
        self.freed: dict[str, dict[str, str]] = {}

    def capabilities(self) -> list[str]:
        """Everything the booking system can be asked to do, read and write alike."""
        return [
            FIND_AVAILABILITY,
            FIND_PATIENT,
            BOOK_SLOT,
            CREATE_APPOINTMENT,
            CANCEL_SLOT,
            CANCEL_APPOINTMENT,
            CONFIRM_ATTENDANCE,
            REBOOK_SLOT,
            UPDATE_CONTACT,
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
            CANCEL_APPOINTMENT: self._cancel_appointment,
            CONFIRM_ATTENDANCE: self._confirm_attendance,
            REBOOK_SLOT: self._rebook_slot,
            UPDATE_CONTACT: self._update_contact,
            LIST_RECORDS: self._list_records,
        }.get(capability)
        if runner is None:
            raise ValueError(f"FakeAgenda cannot run {capability!r}")
        return runner(args)

    def find_availability(self, day: Any, specialty: Any = None) -> list[dict[str, str]]:
        """Up to three free slots on `day` (YYYY-MM-DD), for a specialty when one is named."""
        when = _parse_day(day)
        offered = {slot["id"]: slot for slot in slots.free_slots(self.seed, when, specialty)}
        offered.update({slot["id"]: slot for slot in self._given_back(when, specialty)})
        return sorted(offered.values(), key=lambda slot: slot["when"])[: slots.MAX_SLOTS]

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
        """Open a cita for somebody the book did not hold; 13:00 is refused here too."""
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
        self.freed.pop(identifier, None)  # taken: an hour given back is offered once
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
        """One step of a rescheduling: the hour is released and `rebook_slot` can take it back."""
        return self._set_status(args, "cancelled")

    def _cancel_appointment(self, args: dict[str, Any]) -> dict[str, str]:
        """The whole errand: the patient is not coming, and their hour goes back into the pool."""
        cancelled = self._set_status(args, "cancelled")
        self._release(cancelled["appointment_id"])
        return cancelled

    def _confirm_attendance(self, args: dict[str, Any]) -> dict[str, str]:
        """The patient rang to say they are coming: mark the cita confirmed, hour untouched."""
        return self._set_status(args, "confirmed")

    def _rebook_slot(self, args: dict[str, Any]) -> dict[str, str]:
        """Undo a cancel: the appointment the saga released goes back on the book as it was."""
        return self._set_status(args, "booked")

    def _update_contact(self, args: dict[str, Any]) -> dict[str, str]:
        """Write the caller's new number onto their record, and file the change for the console."""
        change = patients.update_phone(
            self.book, str(args.get("appointment_id", "")), str(args.get("phone", ""))
        )
        self._file(change["appointment_id"], RECONTACTED, CHANGED)
        return change

    def _set_status(self, args: dict[str, Any], status: str) -> dict[str, str]:
        """Write one word onto a row the book really holds, and file how it now stands."""
        appointment_id = str(args.get("appointment_id", ""))
        appointment = self.book.get(appointment_id)
        if appointment is None:
            raise ValueError(f"unknown appointment {appointment_id!r}")
        appointment["status"] = status
        self.released = self.released or status == "cancelled"
        self._file(appointment_id, *STATES.get(status, (BOOKED, PLAIN)))
        return {"appointment_id": appointment_id, "status": status}

    def _release(self, appointment_id: str) -> None:
        """Put the hour a cancelled cita held back on the day it was on."""
        row = self.book.get(appointment_id) or {}
        when, doctor = row.get("when"), row.get("doctor")
        if not when or not doctor:
            return
        moment = datetime.datetime.fromisoformat(when)
        identifier = slots.slot_id(
            moment.date(), moment.time(), specialty_key(row.get("specialty"))
        )
        self.freed[identifier] = {"id": identifier, "when": when, "doctor": doctor}

    def _given_back(self, day: datetime.date, specialty: Any) -> list[dict[str, str]]:
        """The hours cancelled in this session that a caller asking for `day` may be offered."""
        wanted = slots.slot_id(day, datetime.time(), specialty_key(specialty))
        return [
            slot
            for slot in self.freed.values()
            if slot["when"].startswith(day.isoformat()) and slot["id"][-4:] == wanted[-4:]
        ]

    def _list_records(self, _args: dict[str, Any]) -> dict[str, Any]:
        """The appointment book as an operator reads it: every cita, and how each one stands."""
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
            "state": state or STATES.get(row.get("status", ""), (BOOKED, PLAIN))[0],
            "tone": tone or STATES.get(row.get("status", ""), (BOOKED, PLAIN))[1],
            "detail": row.get("specialty") or None,
            "at": time.time() if state else None,
        }


def summarise_availability(slots: list[dict[str, str]] | None) -> str:
    """What `find_availability` may leave in the session log: the hours and who consults them."""
    if not slots:
        return NO_SLOTS
    return f"{len(slots)} free slots: " + "; ".join(
        f"{slot.get('when', '?')} {slot.get('doctor', '?')}" for slot in slots
    )


def summarise_patient(appointment: dict[str, str] | None) -> str:
    """What `find_patient` may leave in the log: when, with whom, and a name the mask blanks."""
    if not appointment:
        return NO_PATIENT
    return (
        f"appointment {appointment.get('appointment_id', '?')} "
        f"for {appointment.get('patient', '?')} "
        f"on {appointment.get('when', '?')} with {appointment.get('doctor', '?')}"
    )


def summarise_contact(change: dict[str, str] | None) -> str:
    """What `update_contact` may leave in the log: whose record moved, and to which tail."""
    if not change:
        return NO_CONTACT
    return (
        f"appointment {change.get('appointment_id', '?')} "
        f"now reachable on a number ending {patients.last_digits(change.get('phone'))}"
    )


def summarise_change(change: dict[str, str] | None) -> str:
    """What a write did to the book: the appointment it touched, and how it now stands."""
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
