"""What the stages hand the model, and what they hand the shop's systems.

The tools themselves are methods of the stage that owns them (`stages/`), so a
reader opens one file and sees the model's whole surface for that step of the
call. This module holds the pieces those tools share: turning an order row into
a line the model can read aloud, the sentence the customer has to say yes to,
the SMS a cancellation ends with, the incident lines the helpdesk answers with,
and the things that can be told to the model when a tool cannot do what was
asked.

Pure functions, no context and no I/O, which is why every rule below is a
one-line unit test.
"""

from convo.lang import es

from ...adapters import ticketbook

RETURN_POLICY = (
    "cuando le llegue tiene 30 días para devolverlo gratis: pide la devolución en «Mis "
    "pedidos», imprime la etiqueta prepagada y lo deja en Correos o en un punto MRW, y el "
    "dinero le vuelve en cuanto la prenda llegue al almacén"
)

NOT_FOUND = (
    "No aparece ningún pedido con esos datos. Pídele que te repita el número de pedido, o el "
    "móvil con el que lo hizo, por si se ha oído mal. Si sigue sin aparecer, dile que lo "
    "compruebe en «Mis pedidos» de la web o que escriba a hola@tiendasur.es."
)
NOT_CONFIRMED = (
    "El cliente no ha confirmado, así que no se ha cancelado nada y el pedido sigue tal cual. "
    "Pregúntale qué prefiere hacer."
)
NOTICE_FAILED = (
    "El SMS de confirmación no ha podido salir, así que el pedido NO se ha cancelado y sigue "
    "exactamente como estaba: nada se ha tocado. Díselo con esas dos ideas —no se ha cancelado "
    "y no ha perdido nada— y pídele un número de móvil válido al que podamos escribirle, "
    "porque sin ese aviso la cancelación no se da por hecha."
)
CANCEL_FAILED = (
    "El almacén no ha podido parar el pedido y no se ha cancelado nada: sigue tal y como "
    "estaba. Díselo, sin culpar al cliente, y ofrécele intentarlo otra vez."
)

# The shop's rule, as the information sheet states it: only an order still in the warehouse
# can be stopped. It is written here as well as in the order system on purpose — the system
# is the last word on what may happen to an order, and this is what the conversation needs
# in order to explain itself before it asks anybody for a yes.
CANCELLABLE = ("preparando",)

STATUS_NOTES = {
    "preparando": "todavía en el almacén, así que aún se puede cancelar",
    "enviado": "ya lo tiene el transportista, así que ya no se puede cancelar",
    "entregado": "ya está entregado, así que lo que cabe es una devolución",
    "cancelado": "el pedido ya está cancelado y el importe está de vuelta",
}

NO_TICKET = (
    "No consta ninguna incidencia con esos datos. Pídele que te repita el número —empieza por "
    "TS-T y son cuatro cifras— o el móvil con el que llamó, por si se ha oído mal. Si sigue sin "
    "aparecer, ofrécele abrirle una nueva ahora mismo."
)
NO_SUBJECT = (
    "Todavía no te ha contado qué le pasa, así que no hay nada que escribir en la incidencia. "
    "Pregúntaselo con una sola pregunta y ábrela cuando te lo haya dicho."
)


def ticket_subject(text: str | None) -> str:
    """The customer's own words as the helpdesk will store them — trimmed, never rewritten.

    One line of indirection on purpose: the stage asks the project what a
    subject is, and the project asks the system that has to hold it. A shop
    that swaps `FakeTickets` for a real helpdesk with a 120-character field
    changes one constant and the prompt above it stops promising more.
    """
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
    """What the model is told the moment an incident exists: the number, and to read it out.

    The number is the whole point of the turn — it is what the customer writes
    on the back of an envelope and quotes on the next call — so the instruction
    to say it out loud, digit by digit, is here and not left to the prompt: a
    tool that returns an identifier nobody repeats has helped no one.
    """
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
    """The sentence the customer has to say yes to, rendered by us and never by the model.

    A confirmation the model writes is a confirmation the model can soften, and
    "¿te lo cancelo entonces?" after three sentences about sizes is not consent
    to stop an order. The words are built here from the row the order system
    returned, so what the customer agrees to and what the platform cancels are
    the same thing by construction.
    """
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
    """What the model is told when the warehouse can no longer stop an order.

    The refusal and the way out in one string, because they are one thing to say:
    a customer who hears "no se puede" and nothing else has been given a problem
    instead of an answer. The policy sentence is `RETURN_POLICY`, quoted from the
    shop's own information sheet so the two can never drift apart.
    """
    return (
        f"Ese pedido está {order['status']} y ya no se puede cancelar: "
        f"{STATUS_NOTES.get(order['status'], '')}. Díselo sin rodeos, en una frase, y ofrécele "
        f"la devolución gratuita: {RETURN_POLICY}. No le prometas ninguna cancelación."
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
