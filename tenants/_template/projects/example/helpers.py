"""Pure helpers the stages share: parse what the caller said, word what the systems answered."""

ACTIVE = "activa"


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
    """The sentence the customer says yes to, rendered by us and never by the model."""
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
