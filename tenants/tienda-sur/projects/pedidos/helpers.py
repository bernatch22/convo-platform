"""Pure helpers the stages share: parse what the caller said, word what the systems answered."""

from convo.lang import es

from ...adapters import ticketbook
from . import messages

CANCELLABLE = ("preparando",)

STATUS_NOTES = {
    "preparando": "todavía en el almacén, así que aún se puede cancelar",
    "enviado": "ya lo tiene el transportista, así que ya no se puede cancelar",
    "entregado": "ya está entregado, así que lo que cabe es una devolución",
    "cancelado": "el pedido ya está cancelado y el importe está de vuelta",
}


def ticket_subject(text: str | None) -> str:
    """The customer's own words as the helpdesk will store them — trimmed, never rewritten."""
    return ticketbook.subject_of(text)


def ticket_line(ticket: dict[str, str]) -> str:
    """The incident as the model reads it back: number, state, what it is about, who has it."""
    return "\n".join(
        [
            f"Incidencia {ticket['ticket_id']}, a nombre de {ticket['name'] or 'quien llamó'}.",
            f"Estado: {ticket['status']} ({ticketbook.STATUS_NOTES.get(ticket['status'], '')}).",
            f"Abierta el {es.spanish_date(ticket.get('opened', '')) or 'sin fecha'}, "
            f"la lleva {ticket.get('team') or 'atención al cliente'}.",
            f"Asunto tal y como se anotó: {ticket['subject']}.",
            _about_order(ticket),
        ]
    )


def opened_line(ticket: dict[str, str]) -> str:
    """What the model is told the moment an incident exists: the number, and to read it out."""
    return (
        f"Incidencia abierta con el número {ticket['ticket_id']}, en estado "
        f"{ticket['status']}. Dile el número despacio, dile que un compañero la mira y que "
        "le escribimos al correo o al móvil de la compra. Se anotó esto y solo esto: "
        f"{ticket['subject']}. No prometas plazos ni compensaciones que no estén en la "
        "información de la tienda."
    )


def order_line(order: dict[str, str]) -> str:
    """The order as the model reads it back: state, contents, amount, delivery and tracking."""
    return "\n".join(
        [
            f"Pedido {order['order_id']}, a nombre de {order['name']}.",
            f"Estado: {order['status']} ({STATUS_NOTES.get(order['status'], '')}).",
            f"Contenido: {order['items']}. Importe: {order['total']}.",
            _delivery(order),
            _tracking(order),
        ]
    )


def cancellable(order: dict[str, str]) -> bool:
    """Whether this order can still be stopped: only while the warehouse is preparing it."""
    return order.get("status") in CANCELLABLE


def confirmation_question(order: dict[str, str]) -> str:
    """The sentence the customer has to say yes to, rendered by us and never by the model."""
    return (
        f"Te cancelo entonces el pedido {order['order_id']}, el de {order['total']}, "
        "y el importe te vuelve por donde lo pagaste. ¿Lo cancelo?"
    )


def sms_text(order: dict[str, str]) -> str:
    """The message the shop sends when a cancellation is done; short enough for one SMS."""
    return (
        f"Tienda Sur: tu pedido {order['order_id']} queda cancelado. El importe de "
        f"{order['total']} vuelve por donde lo pagaste en 3 a 5 días laborables. "
        "Dudas: 954 000 000."
    )


def cannot_cancel(order: dict[str, str]) -> str:
    """What the model is told when the warehouse can no longer stop an order."""
    return (
        f"Ese pedido está {order['status']} y ya no se puede cancelar: "
        f"{STATUS_NOTES.get(order['status'], '')}. Díselo sin rodeos, en una frase, y ofrécele "
        f"la devolución gratuita: {messages.RETURN_POLICY}. No le prometas ninguna cancelación."
    )


def _delivery(order: dict[str, str]) -> str:
    """The delivery line: who carries it and for when it is expected."""
    day = es.spanish_date(order.get("eta", ""))
    when = f"entrega prevista el {day}" if day else "sin fecha de entrega todavía"
    return f"Envío: {order['shipping']} con {order['carrier']}; {when}."


def _tracking(order: dict[str, str]) -> str:
    """The tracking line: the code, or why there is not one yet."""
    if order.get("tracking"):
        return f"Seguimiento: {order['tracking']}, en la web de {order['carrier']}."
    return "Seguimiento: todavía no tiene número; sale en cuanto el paquete deje el almacén."


def _about_order(ticket: dict[str, str]) -> str:
    """The order the incident is about, when the helpdesk recorded one; never invented."""
    if ticket.get("order_id"):
        return f"Va sobre el pedido {ticket['order_id']}."
    return "No está asociada a ningún pedido concreto."
