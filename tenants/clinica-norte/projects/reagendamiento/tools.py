"""What the stages hand the model, and what they hand the clinic's systems.

The tools themselves are methods of the stage that owns them (`stages/`), so a
reader opens one file and sees the model's whole surface for that step of the
call. This module holds the pieces those tools share: turning the caller's
words into a date, turning the agenda's rows into a line the model can read
aloud, and writing the SMS a rebooking ends with.

Pure functions, no context and no I/O, which is why every rule below is a
one-line unit test.
"""

import datetime

from . import dates

UNREADABLE_DATE = "No he entendido para qué día lo quiere. ¿Me dice el día de la semana o la fecha?"
OFFER_LIMIT = 2
MORE_LEFT = "(Ese día queda algún hueco más: ofrécelo solo si ninguno de estos dos le sirve.)"

NO_SUCH_HOUR = (
    "Esa hora no es una de las que le he ofrecido. Vuelve a mirar la agenda de ese día "
    "y ofrécele las horas que te devuelva."
)
BOOKING_FAILED = (
    "El sistema de citas ha rechazado esa hora y no se ha guardado nada: la cita que el "
    "paciente ya tenía sigue en pie, tal cual estaba. Díselo con estas dos ideas —no ha "
    "podido reservarse y su cita anterior no se ha tocado— y ofrécele otra hora."
)
NOT_CONFIRMED = (
    "El paciente no ha confirmado, así que no se ha reservado nada. Pregúntale qué prefiere "
    "hacer y ofrécele otra hora si la quiere."
)


def resolve_day(text: str, today: datetime.date) -> datetime.date:
    """The day the caller means, or ValueError; the stage turns that into a spoken sentence."""
    return dates.resolve(text, today)


def offer(day: datetime.date, slots: list[dict[str, str]]) -> str:
    """What the model reads back after a lookup: the hours to offer, or a plain 'no hay'."""
    return _offer(day, slots)


def sms_text(patient: str, slot: dict[str, str]) -> str:
    """The message the clinic sends when a change is done; short enough for one SMS."""
    return (
        f"Clínica Norte: {patient}, su cita queda el {dates.spanish_moment(slot['when'])} "
        f"con {slot['doctor']}. Para cambiarla llame al 910 000 000."
    )


def confirmation_question(slot: dict[str, str]) -> str:
    """The sentence the caller has to say yes to, rendered by us and never by the model.

    A confirmation the model writes is a confirmation the model can soften, and
    "¿le va bien el jueves?" is not consent to move an appointment. The words
    are built here from the row the agenda returned, so what the caller agrees
    to and what the platform books are the same thing by construction.
    """
    return f"{dates.spoken_moment(slot['when'])} con {slot['doctor']}, ¿lo confirmo?"


def _offer(day: datetime.date, slots: list[dict[str, str]]) -> str:
    """The two hours to offer, or a plain 'no hay' for that day.

    Two, not the three the agenda returns, because how many options a caller can
    hold in their head on a phone call is a decision this project makes once —
    not arithmetic the model has to do under pressure every turn. Asking it in
    the prompt to name two out of a list of three produced exactly the sentence
    you would expect: three hours read out, then "¿cuál de las dos primeras?".
    The rest of the day is not lost; the last line says so, and the model asks
    again if neither works.

    The agenda's slot id is deliberately left out. Everything in here is text a
    voice agent may read aloud, and `sl-20260903-1100-trau` is not a sentence.
    The stage keeps the ids for itself and the model chooses by the hour it
    just offered, which is also what the patient says out loud.
    """
    if not slots:
        return f"Sin huecos libres el {dates.spanish_day(day)}."
    lines = [f"- {dates.spanish_moment(s['when'])}, {s['doctor']}" for s in slots[:OFFER_LIMIT]]
    text = f"Huecos libres el {dates.spanish_day(day)}:\n" + "\n".join(lines)
    return f"{text}\n{MORE_LEFT}" if len(slots) > OFFER_LIMIT else text
