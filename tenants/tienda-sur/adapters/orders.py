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

from typing import Any

from core.adapters.base import Adapter

from . import orderbook
from .orderbook import CANCELLED, DELIVERED, PREPARING, SHIPPED  # re-exported: the statuses

FIND_ORDER = "find_order"
CANCEL_ORDER = "cancel_order"
RESTORE_ORDER = "restore_order"

__all__ = ["CANCELLED", "DELIVERED", "PREPARING", "SHIPPED", "FakeOrders"]


class FakeOrders(Adapter):
    """The shop's order system: where an order is, and whether it can still be stopped."""

    def __init__(self) -> None:
        self.book = orderbook.seeded()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def capabilities(self) -> list[str]:
        """Everything the order system can be asked to do, read and write alike."""
        return [FIND_ORDER, CANCEL_ORDER, RESTORE_ORDER]

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        """Run one capability against the book; ValueError on anything it cannot do."""
        self.calls.append((capability, args))
        runner = {
            FIND_ORDER: self._find_order,
            CANCEL_ORDER: self._cancel_order,
            RESTORE_ORDER: self._restore_order,
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
        return {"order_id": order_id, "status": CANCELLED, "refund": order["total"]}

    def _restore_order(self, args: dict[str, Any]) -> dict[str, str]:
        """Undo a cancel: the order the saga stopped goes back into preparation as it was."""
        order_id, order = self._order(args)
        order["status"] = PREPARING
        return {"order_id": order_id, "status": PREPARING}

    def _order(self, args: dict[str, Any]) -> tuple[str, dict[str, str]]:
        order_id = orderbook.normalise(str(args.get("order_id", "")))
        order = self.book.get(order_id)
        if order is None:
            raise ValueError(f"unknown order {args.get('order_id')!r}")
        return order_id, order
