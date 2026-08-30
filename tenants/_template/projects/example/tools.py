"""What the stages share: how a booking is read aloud, and what is said when a tool cannot.

The tools themselves are methods of the stage that owns them (`stages/`), so a
reader opens one file and sees the model's whole surface for that step of the
call. This module holds the pieces those tools share.

Pure functions, no context and no I/O, which is why every rule below is a
one-line unit test.

TODO(copy): the sentences are the business's, not the platform's — rewrite them
in your register and your language.
"""

ACTIVE = "activa"

NOT_FOUND = (
    "No aparece ninguna reserva con esos datos. Pídale que le repita la referencia, por si "
    "se ha oído mal. Si sigue sin aparecer, dígale que la busque en el correo de "
    "confirmación o que escriba a hola@example.test."
)
NOT_CONFIRMED = (
    "El cliente no ha confirmado, así que no se ha cancelado nada y la reserva sigue tal "
    "cual. Pregúntele qué prefiere hacer."
)


def booking_line(booking: dict[str, str]) -> str:
    """The booking as the model reads it back: reference, name, service, day and state."""
    return (
        f"Reserva {booking['reference']}, a nombre de {booking['name']}. "
        f"Servicio: {booking['service']}, el {booking['when']}. "
        f"Estado: {booking['status']}."
    )


def cancellable(booking: dict[str, str]) -> bool:
    """Whether this booking can still be stopped: only while it is active."""
    return booking.get("status") == ACTIVE


def confirmation_question(booking: dict[str, str]) -> str:
    """The sentence the customer says yes to, rendered by us and never by the model.

    A confirmation the model writes is one the model can soften. Building it
    here, from the row the system returned, is what makes what the customer
    agreed to and what the platform cancels the same thing by construction.
    """
    return (
        f"Le cancelo entonces la reserva {booking['reference']}, la del "
        f"{booking['when']}. ¿La cancelo?"
    )


def cannot_cancel(booking: dict[str, str]) -> str:
    """What the model is told when the booking can no longer be stopped."""
    return (
        f"Esa reserva está {booking['status']} y ya no se puede cancelar. Dígaselo en una "
        "frase y ofrézcale hacer una nueva. No le prometa ninguna cancelación."
    )
