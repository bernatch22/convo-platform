"""The orders Tienda Sur already has in its system, as a seeded demo book.

Decisions: docs/decisions/tenants.tienda-sur.adapters.orderbook.md
"""

PREPARING = "preparando"
SHIPPED = "enviado"
DELIVERED = "entregado"
CANCELLED = "cancelado"

# order number -> the order as the shop's system holds it today.
ORDERS: dict[str, dict[str, str]] = {
    "TS-10432": {
        "name": "Marta Alonso Gil",
        "phone": "600222333",
        "status": PREPARING,
        "placed": "2026-08-27",
        "items": "2 camisetas de algodón talla M y un pantalón chino talla 42",
        "total": "74,90 euros",
        "carrier": "Correos Express",
        "tracking": "",
        "eta": "2026-09-02",
        "shipping": "envío estándar",
    },
    "TS-10433": {
        "name": "Javier Nieto Salas",
        "phone": "600444555",
        "status": SHIPPED,
        "placed": "2026-08-25",
        "items": "una sudadera con capucha talla L y un gorro de lana",
        "total": "129,00 euros",
        "carrier": "Correos Express",
        "tracking": "CE884512377ES",
        "eta": "2026-09-01",
        "shipping": "envío exprés",
    },
    "TS-10434": {
        "name": "Lucía Ferrer Blanco",
        "phone": "600666777",
        "status": DELIVERED,
        "placed": "2026-08-20",
        "items": "unas zapatillas de lona talla 39",
        "total": "45,50 euros",
        "carrier": "SEUR",
        "tracking": "SE773210984ES",
        "eta": "2026-08-26",
        "shipping": "envío estándar",
    },
    # The demo's deterministic failure: the order is cancellable, but the number on it is a
    # landline and the SMS gateway only writes to mobiles. Cancelling it exercises the
    # compensated path — see `FakeSms` and the saga in `stages/order_desk.py`.
    "TS-10435": {
        "name": "Ignacio Prat Vives",
        "phone": "910334455",
        "status": PREPARING,
        "placed": "2026-08-28",
        "items": "un abrigo de paño talla 50",
        "total": "212,40 euros",
        "carrier": "MRW",
        "tracking": "",
        "eta": "2026-09-03",
        "shipping": "envío estándar",
    },
}

CANCELLABLE = (PREPARING,)


def seeded() -> dict[str, dict[str, str]]:
    """A fresh copy of the demo book: one adapter per session must not share state."""
    return {key: dict(value) for key, value in ORDERS.items()}


def lookup(
    book: dict[str, dict[str, str]], number: str | None, phone: str | None
) -> dict[str, str] | None:
    """The order identified by its number or by the phone it was placed with, or None."""
    found = book.get(normalise(number))
    if found is not None:
        return {"order_id": normalise(number), **found}
    digits = _digits(phone)
    orders = [
        {"order_id": key, **order}
        for key, order in book.items()
        if digits and _digits(order["phone"]) == digits
    ]
    return max(orders, key=lambda order: order["placed"]) if orders else None


def normalise(number: str | None) -> str:
    """`ts 10432`, `ts-10432`, `TS10432` — one shape, because it is read out loud."""
    if not isinstance(number, str):
        return ""
    digits = _digits(number)
    return f"TS-{digits}" if digits else ""


def cancellable(order: dict[str, str]) -> bool:
    """Whether the warehouse can still stop this order: only while it is being prepared."""
    return order.get("status") in CANCELLABLE


def _digits(text: str | None) -> str:
    return "".join(c for c in text if c.isdigit()) if isinstance(text, str) else ""
