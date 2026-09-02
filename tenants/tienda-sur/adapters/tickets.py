"""FakeTickets: the shop's incident desk, and the first record this platform CREATES.

Every other fake system here answers about something that already existed when
the phone rang: an order was placed on the web, an appointment was in the book.
A ticket is not. It comes into being mid-call, out of a sentence the customer
said, and it has to be readable by its number on the NEXT call — which is a
different room, a different job and a different process.

That is why this adapter reads the ledger and `FakeOrders` does not. The rule
in `core/adapters/ledger.py` is write-through: a demo adapter records what it
changed so the console can see it, and never reads it back into a conversation,
so no call can be contaminated by what another one wrote. The rule holds
because an order's identity lives in the seeded book — the ledger only ever
carries a NEW STANDING for a row that already existed. A ticket's identity has
nowhere else to live: refuse to read the ledger and `TS-T0003` exists for
exactly as long as the call that opened it, which is not a helpdesk, it is a
sticky note. So this adapter's book is the seed with the ledger merged over it,
in both directions, and the isolation the rule was protecting is kept where it
actually belongs: `tests/conftest.py` gives every test its own ledger file.

It stores the CONSOLE's row shape (`core.adapters.base.LIST_RECORDS`) and reads
tickets back out of it, rather than inventing a second private schema in the
same file. One shape on disk, one reader, and what the operator sees is by
construction what the next call will find.

Open source note: replace each method with an HTTP call to your own helpdesk
(Zendesk, Freshdesk, a table of your own), keep `capabilities()` and the result
shapes, and every layer above — tool, guard, prompt, console — works unchanged.
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
        """The incident queue as an operator reads it: who, about what, and where it stands.

        The console's read, never a tool. The same shop answers this question
        twice in one project and with two different shapes — orders here,
        tickets there — which is the whole reason nothing in `core` holds a list
        of columns or of state words.
        """
        rows = {key: _as_record(key, ticket) for key, ticket in ticketbook.seeded().items()}
        rows.update(self.ledger.rows())
        return {"shape": SHAPE, "labels": LABELS, "rows": list(rows.values())}

    def _file(self, ticket_id: str, ticket: dict[str, str], tone: str) -> None:
        """Record the incident where the next call and the console can both read it."""
        self.ledger.record(ticket_id, _as_record(ticket_id, ticket, tone))


def summarise_ticket(result: Any) -> str:
    """The one line `open_ticket` may leave in the log: the number, and nothing the caller said.

    The number is the point — it is the join key the console reads and the thing
    the customer will quote back next week — and the subject is deliberately not
    here. A ticket's subject is whatever a person dictated into it: their
    address, their neighbour's name, the order somebody else took delivery of.
    The mask would blank the values it knows about; this renderer never hands it
    the field at all.
    """
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
    """One console row read back as the incident it recorded — the inverse of `_as_record`.

    The ledger holds one shape and this is what makes that affordable: the
    helpdesk reads its own rows out of the console's columns instead of a second
    private schema kept in step by hand. `order_id` is the one field the console
    never had a column for, so it is recovered from nothing and stays empty; it
    is a cross-reference for the operator, not something the caller is told.
    """
    return {
        "name": str(row.get("who") or ""),
        "phone": str(row.get("contact") or ""),
        "subject": str(row.get("detail") or ""),
        "status": str(row.get("state") or ""),
        "opened": str(row.get("when") or ""),
        "team": str(row.get("handled_by") or ""),
        "order_id": "",
    }
