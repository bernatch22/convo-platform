"""FakeBookings: the business's booking system, invented but never random.

It stands where your real back office will stand and answers the same shape: a
capability name, a dict of arguments, a plain result. Reading is `find_booking`;
writing is `cancel_booking` and its inverse `restore_booking`, which the saga
runs when the cancellation could not be confirmed to the customer.

TODO(copy): replace each method with an HTTP call to your own API and keep
`capabilities()` and the result shapes. Every layer above — tool, guard, saga,
executor, prompt — then works unchanged. An argument the system cannot read
raises `ValueError`, which the executor turns into a sentence the caller hears;
never a stack trace, and never a silent success.
"""

from typing import Any

from core.adapters.base import Adapter

FIND_BOOKING = "find_booking"
CANCEL_BOOKING = "cancel_booking"
RESTORE_BOOKING = "restore_booking"

ACTIVE, CANCELLED = "activa", "cancelada"

# Two seeded rows, so the goldens and the unit tests have something deterministic to say.
SEED = {
    "EX-1001": {
        "reference": "EX-1001",
        "name": "Ana López",
        "when": "2026-09-03 10:00",
        "service": "revisión",
        "status": ACTIVE,
        "phone": "600111222",
    },
    "EX-1002": {
        "reference": "EX-1002",
        "name": "Luis Marín",
        "when": "2026-09-04 17:30",
        "service": "revisión",
        "status": CANCELLED,
        "phone": "600333444",
    },
}


class FakeBookings(Adapter):
    """The business's booking system: what a customer has booked, and stopping it."""

    def __init__(self) -> None:
        self.book = {key: dict(row) for key, row in SEED.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def capabilities(self) -> list[str]:
        """Everything this system can be asked to do, read and write alike."""
        return [FIND_BOOKING, CANCEL_BOOKING, RESTORE_BOOKING]

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        """Run one capability against the book; ValueError on anything it cannot do."""
        self.calls.append((capability, args))
        runner = {
            FIND_BOOKING: self._find,
            CANCEL_BOOKING: self._cancel,
            RESTORE_BOOKING: self._restore,
        }.get(capability)
        if runner is None:
            raise ValueError(f"FakeBookings cannot run {capability!r}")
        return runner(args)

    def _find(self, args: dict[str, Any]) -> dict[str, str] | None:
        reference = str(args.get("reference", "")).upper().replace(" ", "")
        return self.book.get(reference)

    def _cancel(self, args: dict[str, Any]) -> dict[str, str]:
        """Stop a booking; refused for one that is already cancelled."""
        reference, row = self._row(args)
        if row["status"] != ACTIVE:
            raise ValueError(f"booking {reference} is {row['status']} and cannot be cancelled")
        row["status"] = CANCELLED
        return {"reference": reference, "status": CANCELLED}

    def _restore(self, args: dict[str, Any]) -> dict[str, str]:
        """Undo a cancel: the compensation the saga runs when the customer could not be told."""
        reference, row = self._row(args)
        row["status"] = ACTIVE
        return {"reference": reference, "status": ACTIVE}

    def _row(self, args: dict[str, Any]) -> tuple[str, dict[str, str]]:
        reference = str(args.get("reference", "")).upper().replace(" ", "")
        row = self.book.get(reference)
        if row is None:
            raise ValueError(f"unknown booking {args.get('reference')!r}")
        return reference, row
