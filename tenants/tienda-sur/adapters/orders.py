"""FakeOrders: Tienda Sur's order system, invented but never random.

It stands where the shop's real back office will stand and answers the same
shape: a capability name, a dict of arguments, a plain result. Reading is
`find_order`; writing is `cancel_order` and `restore_order`, the inverse the
saga runs when the customer cannot be told the cancellation went through.

One refusal is deliberate and deterministic, and it is the rule of the whole
project: an order that has already left the warehouse cannot be cancelled. The
adapter raises for it even though the stage checks first — the customer's own
system is the last word on what may happen to an order, and a platform that
only enforced the rule in a prompt would not be enforcing it at all.

Open source note: this file is the template a customer copies. Replace each
method with an HTTP call to your own order API, keep `capabilities()` and the
result shapes, and every layer above (tool, guard, saga, executor, prompt)
works unchanged. An argument the system cannot read raises `ValueError`, which
the executor turns into a sentence the caller hears — never a stack trace.
"""

import time
from typing import Any

from convo.adapters.base import CHANGED, GONE, LIST_RECORDS, PLAIN, Adapter
from convo.adapters.ledger import Ledger

from . import orderbook
from .orderbook import CANCELLED, DELIVERED, PREPARING, SHIPPED  # re-exported: the statuses

FIND_ORDER = "find_order"
CANCEL_ORDER = "cancel_order"
RESTORE_ORDER = "restore_order"

LEDGER_BOOK = "tienda-sur/orders"

# The shop has no agenda and the console must not invent one for it: this project's
# records are ORDERS, and they answer with an order's own columns and an order's own
# statuses. That is what `shape` is for — the business names its records, and the
# console renders whatever it is handed.
SHAPE = "orders"
LABELS = {
    "who": "customer",
    "contact": "phone",
    "when": "placed",
    "handled_by": "carrier",
    "detail": "order",
}

__all__ = ["CANCELLED", "DELIVERED", "PREPARING", "SHIPPED", "FakeOrders"]


class FakeOrders(Adapter):
    """The shop's order system: where an order is, and whether it can still be stopped."""

    def __init__(self, ledger: Ledger | None = None) -> None:
        self.book = orderbook.seeded()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.ledger = ledger or Ledger(LEDGER_BOOK)

    def capabilities(self) -> list[str]:
        """Everything the order system can be asked to do, read and write alike."""
        return [FIND_ORDER, CANCEL_ORDER, RESTORE_ORDER, LIST_RECORDS]

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        """Run one capability against the book; ValueError on anything it cannot do."""
        self.calls.append((capability, args))
        runner = {
            FIND_ORDER: self._find_order,
            CANCEL_ORDER: self._cancel_order,
            RESTORE_ORDER: self._restore_order,
            LIST_RECORDS: self._list_records,
        }.get(capability)
        if runner is None:
            raise ValueError(f"FakeOrders cannot run {capability!r}")
        return runner(args)

    def cancelled(self) -> list[str]:
        """Every order this session cancelled, in the order it cancelled them."""
        return [key for key, order in self.book.items() if order["status"] == CANCELLED]

    def _find_order(self, args: dict[str, Any]) -> dict[str, str] | None:
        return orderbook.lookup(self.book, args.get("order_id"), args.get("phone"))

    def _cancel_order(self, args: dict[str, Any]) -> dict[str, str]:
        """Stop an order in the warehouse; refused for anything already on its way."""
        order_id, order = self._order(args)
        if not orderbook.cancellable(order):
            raise ValueError(f"order {order_id} is {order['status']} and can no longer be stopped")
        order["status"] = CANCELLED
        self._file(order_id, GONE)
        return {"order_id": order_id, "status": CANCELLED, "refund": order["total"]}

    def _restore_order(self, args: dict[str, Any]) -> dict[str, str]:
        """Undo a cancel: the order the saga stopped goes back into preparation as it was."""
        order_id, order = self._order(args)
        order["status"] = PREPARING
        self._file(order_id, CHANGED)
        return {"order_id": order_id, "status": PREPARING}

    def _list_records(self, _args: dict[str, Any]) -> dict[str, Any]:
        """The order book as an operator reads it: every order, and where each one stands.

        The console's read, never a tool. The shop answers the same question the
        clinic does and with a different shape — `orders`, with an order's own
        columns — which is the whole reason nothing in `core` holds a list of
        columns: a project with no agenda is not an empty agenda.

        The seeded book is what the shop held before anyone rang; the ledger is
        every order a call has changed since, across processes, and it wins
        wherever both hold the same number.
        """
        rows = {key: self._as_record(key, order) for key, order in self.book.items()}
        rows.update(self.ledger.rows())
        return {"shape": SHAPE, "labels": LABELS, "rows": list(rows.values())}

    def _file(self, order_id: str, tone: str) -> None:
        """Record the order's new standing where a second process can read it."""
        order = self.book.get(order_id)
        if order is not None:
            self.ledger.record(order_id, self._as_record(order_id, order, tone))

    def _as_record(self, order_id: str, order: dict[str, str], tone: str = "") -> dict[str, Any]:
        """One order in the shape the console reads (`core.adapters.base.LIST_RECORDS`)."""
        return {
            "id": order_id,
            "who": order.get("name", ""),
            "contact": order.get("phone") or None,
            "when": order.get("placed") or None,
            "handled_by": order.get("carrier") or None,
            "state": order.get("status", ""),
            "tone": tone or (GONE if order.get("status") == CANCELLED else PLAIN),
            "detail": order.get("items") or None,
            "at": time.time() if tone else None,
        }

    def _order(self, args: dict[str, Any]) -> tuple[str, dict[str, str]]:
        order_id = orderbook.normalise(str(args.get("order_id", "")))
        order = self.book.get(order_id)
        if order is None:
            raise ValueError(f"unknown order {args.get('order_id')!r}")
        return order_id, order
