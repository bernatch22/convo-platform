"""FakeTickets: the shop's incident desk, and the first record this platform CREATES.

Decisions: docs/decisions/tenants.tienda-sur.adapters.tickets.md
"""

import time
from typing import Any

from convo.adapters.base import GONE, LIST_RECORDS, NEW, PLAIN, Adapter
from convo.adapters.ledger import Ledger

from . import ticketbook
from .ticketbook import IN_PROGRESS, OPEN, RESOLVED  # re-exported: the states

OPEN_TICKET = "open_ticket"
TICKET_STATUS = "ticket_status"

LEDGER_BOOK = "tienda-sur/tickets"

# The shop's incidents are not its orders: they have a subject instead of a basket, a team
# instead of a carrier, and three states of their own. `shape` is what says so — the
# business names its records and the console renders whatever it is handed.
SHAPE = "tickets"
LABELS = {
    "who": "customer",
    "contact": "phone",
    "when": "opened",
    "handled_by": "team",
    "detail": "asunto",
}

NOTHING_WRITTEN = "no ticket"

__all__ = ["IN_PROGRESS", "OPEN", "RESOLVED", "FakeTickets", "summarise_ticket"]


class FakeTickets(Adapter):
    """The shop's helpdesk: open an incident, and say how the customer's own one stands."""

    def __init__(self, ledger: Ledger | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.ledger = ledger or Ledger(LEDGER_BOOK)

    def capabilities(self) -> list[str]:
        """Everything the helpdesk can be asked to do: one write, one read, one console view."""
        return [OPEN_TICKET, TICKET_STATUS, LIST_RECORDS]

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        """Run one capability against the book; ValueError on anything it cannot do."""
        self.calls.append((capability, args))
        runner = {
            OPEN_TICKET: self._open_ticket,
            TICKET_STATUS: self._ticket_status,
            LIST_RECORDS: self._list_records,
        }.get(capability)
        if runner is None:
            raise ValueError(f"FakeTickets cannot run {capability!r}")
        return runner(args)

    def book(self) -> dict[str, dict[str, str]]:
        """Every incident the shop holds: the seeded ones, and every one a call has opened."""
        tickets = ticketbook.seeded()
        tickets.update({key: _as_ticket(row) for key, row in self.ledger.rows().items()})
        return tickets

    def _open_ticket(self, args: dict[str, Any]) -> dict[str, str]:
        """File the customer's problem as a new incident and hand back the number to read out."""
        subject = ticketbook.subject_of(args.get("subject"))
        if not subject:
            raise ValueError("a ticket needs a subject: the customer's own words")
        book = self.book()
        ticket_id = ticketbook.mint(book)
        ticket = {
            "name": str(args.get("name") or ""),
            "phone": str(args.get("phone") or ""),
            "subject": subject,
            "status": ticketbook.OPEN,
            "opened": time.strftime("%Y-%m-%d"),
            "team": ticketbook.TEAM,
            "order_id": str(args.get("order_id") or ""),
        }
        self._file(ticket_id, ticket, NEW)
        return {
            "ticket_id": ticket_id,
            "status": ticket["status"],
            "subject": subject,
            "order_id": ticket["order_id"],
        }

    def _ticket_status(self, args: dict[str, Any]) -> dict[str, str] | None:
        """The incident by its number, or the customer's most recent one by their phone."""
        return ticketbook.lookup(self.book(), args.get("ticket_id"), args.get("phone"))

    def _list_records(self, _args: dict[str, Any]) -> dict[str, Any]:
        """The incident queue as an operator reads it: who, about what, and where it stands."""
        rows = {key: _as_record(key, ticket) for key, ticket in ticketbook.seeded().items()}
        rows.update(self.ledger.rows())
        return {"shape": SHAPE, "labels": LABELS, "rows": list(rows.values())}

    def _file(self, ticket_id: str, ticket: dict[str, str], tone: str) -> None:
        """Record the incident where the next call and the console can both read it."""
        self.ledger.record(ticket_id, _as_record(ticket_id, ticket, tone))


def summarise_ticket(result: Any) -> str:
    """The one line `open_ticket` may leave in the log: the number, and nothing the caller said."""
    if not isinstance(result, dict) or not result.get("ticket_id"):
        return NOTHING_WRITTEN
    return f"ticket {result['ticket_id']} {result.get('status', '?')}"


def _as_record(ticket_id: str, ticket: dict[str, str], tone: str = "") -> dict[str, Any]:
    """One incident in the shape the console reads (`core.adapters.base.LIST_RECORDS`)."""
    return {
        "id": ticket_id,
        "who": ticket.get("name", ""),
        "contact": ticket.get("phone") or None,
        "when": ticket.get("opened") or None,
        "handled_by": ticket.get("team") or None,
        "state": ticket.get("status", ""),
        "tone": tone or (GONE if ticket.get("status") == RESOLVED else PLAIN),
        "detail": ticket.get("subject") or None,
        "at": time.time() if tone else None,
    }


def _as_ticket(row: dict[str, Any]) -> dict[str, str]:
    """One console row read back as the incident it recorded — the inverse of `_as_record`."""
    return {
        "name": str(row.get("who") or ""),
        "phone": str(row.get("contact") or ""),
        "subject": str(row.get("detail") or ""),
        "status": str(row.get("state") or ""),
        "opened": str(row.get("when") or ""),
        "team": str(row.get("handled_by") or ""),
        "order_id": "",
    }
