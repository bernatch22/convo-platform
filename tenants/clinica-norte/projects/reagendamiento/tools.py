"""What the stages hand the model, and what they hand the clinic's systems.

The tools themselves are methods of the stage that owns them (`stages/`), so a
reader opens one file and sees the model's whole surface for that step of the
call. This module holds the pieces those tools share: turning the caller's
words into a date and an hour, turning the agenda's rows into a line the model
can read aloud, and writing the SMS a booking ends with. Both booking stages —
the one that moves a cita and the one that creates it — read from here, which is
the whole reason it is a module and not two sets of private helpers.

Pure functions, no context and no I/O, which is why every rule below is a
one-line unit test.
"""

import datetime
import re

from ...adapters import patients
from . import dates

HHMM = re.compile(r"(\d{1,2})\s*[:.hy ]?\s*(\d{2})?")

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
NEW_BOOKING_FAILED = (
    "El sistema de citas ha rechazado esa hora y no se ha guardado nada: el paciente sigue "
    "sin ninguna cita apuntada. Díselo con estas dos ideas —no ha podido reservarse y no le "
    "queda nada a su nombre— y ofrécele otra hora."
)

UNREADABLE_PHONE = (
    "Ese número no son nueve cifras, así que no se ha cambiado nada. Pídele que te lo repita "
    "cifra a cifra y vuelve a llamar a la herramienta con el número entero."
)
CONTACT_NOT_CONFIRMED = (
    "El paciente no ha confirmado, así que su teléfono sigue siendo el que ya constaba. "
    "Pregúntale qué prefiere hacer y no vuelvas a intentarlo sin que te lo pida."
)
CONTACT_UPDATE_FAILED = (
    "La ficha del paciente no ha aceptado el cambio y su teléfono sigue siendo el que ya "
    "constaba. Díselo tal cual —no se ha podido cambiar y el número de antes sigue en pie— y "
    "ofrécele que lo intentemos de nuevo o que pase por recepción."
)


def resolve_day(text: str, today: datetime.date) -> datetime.date:
    """The day the caller means, or ValueError; the stage turns that into a spoken sentence."""
    return dates.resolve(text, today)


def hour_of(when: str) -> str:
    """`2026-09-03T11:00` becomes `11:00`: the hour is how the caller names a slot."""
    return when.split("T")[1][:5]


def normalise_hour(time: str) -> str:
    """`11`, `11:00`, `11.00`, `11h` — one shape, so a small variation is not a refusal."""
    match = HHMM.search(time or "")
    if not match:
        return ""
    return f"{int(match.group(1)):02d}:{match.group(2) or '00'}"


def offer(day: datetime.date, slots: list[dict[str, str]]) -> str:
    """What the model reads back after a lookup: the hours to offer, or a plain 'no hay'."""
    return _offer(day, slots)


def sms_text(patient: str, slot: dict[str, str]) -> str:
    """The message the clinic sends when a change is done; short enough for one SMS."""
    return (
        f"Clínica Norte: {patient}, su cita queda el {dates.spanish_moment(slot['when'])} "
        f"con {slot['doctor']}. Para cambiarla llame al 910 000 000."
    )


def masked_phone(phone: str | None) -> str:
    """`600123456` → `acaba en 456`: the only thing reception may say about a number on file.

    Validation without disclosure, which is the whole shape of this errand. The
    patient rings because the number the clinic holds is wrong, so the agent has
    to make sure they are both talking about the same record — and reading nine
    digits out to whoever picked up the phone would hand a stranger the very
    datum the call is about to change. Three digits are recognised instantly by
    the person who owns them and are worth nothing to anybody else, which is why
    every bank in Spain says a number this way.

    `patients.last_digits` is the tail, this is the sentence: one place decides
    how much, one place decides how it sounds.
    """
    return f"acaba en {patients.last_digits(phone)}"


def normalise_phone(said: str | None) -> str:
    """The digits of a number the caller read out, or "" — `689 00 01 11` and `689000111` are one.

    Spoken numbers arrive with spaces, dots and dashes in them, and a Spanish
    mobile is nine digits. Anything shorter is a number that was misheard rather
    than a number that was given, and the stage asks again instead of writing it.
    """
    digits = "".join(character for character in (said or "") if character.isdigit())
    return digits if len(digits) == patients.PHONE_DIGITS else ""


def spoken_phone(phone: str) -> str:
    """`689000111` → `689 000 111`: a number grouped so a TTS reads it as a phone number.

    Nine digits in a row are read out as one enormous cardinal — «seiscientos
    ochenta y nueve millones…» — which is not a number anybody can check against
    the one they just said. Three groups of three is how the number is printed
    on every Spanish document and how it is said out loud.
    """
    return " ".join(phone[index : index + 3] for index in range(0, len(phone), 3))


def contact_confirmation_question(phone: str) -> str:
    """The sentence the caller has to say yes to before the clinic changes how it reaches them.

    Rendered here from the digits the platform is about to write, never by the
    model, for the same reason as the two booking questions: what the caller
    agreed to and what is written have to be the same thing by construction. The
    NEW number is read out whole — the caller said it seconds ago, and a
    confirmation that masked it would be asking somebody to agree to a number
    they cannot hear.
    """
    return f"Su nuevo teléfono de contacto sería el {spoken_phone(phone)}. ¿Se lo cambio?"


def confirmation_question(slot: dict[str, str]) -> str:
    """The sentence the caller has to say yes to, rendered by us and never by the model.

    A confirmation the model writes is a confirmation the model can soften, and
    "¿le va bien el jueves?" is not consent to move an appointment. The words
    are built here from the row the agenda returned, so what the caller agrees
    to and what the platform books are the same thing by construction.
    """
    return f"{dates.spoken_moment(slot['when'])} con {slot['doctor']}, ¿lo confirmo?"


def new_confirmation_question(slot: dict[str, str]) -> str:
    """The sentence a caller with no cita has to say yes to before one is written for them.

    Same rule as `confirmation_question` and a different verb: nothing is being
    moved, so «¿lo confirmo?» would be asking about a change that does not
    exist. «¿se la reservo?» names what the platform is about to do, and the day,
    the hour and the professional come off the agenda's own row.
    """
    return f"{dates.spoken_moment(slot['when'])} con {slot['doctor']}, ¿se la reservo?"


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
