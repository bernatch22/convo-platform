"""Pure helpers the stages share: parse what the caller said, word what the systems answered."""

import datetime
import re

from convo.lang import es

from ...adapters import patients
from . import messages

HHMM = re.compile(r"(\d{1,2})\s*[:.hy ]?\s*(\d{2})?")

OFFER_LIMIT = 2


def resolve_day(text: str, today: datetime.date) -> datetime.date:
    """The day the caller means, or ValueError; the stage turns that into a spoken sentence."""
    return es.resolve(text, today)


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
        f"Clínica Norte: {patient}, su cita queda el {es.spanish_moment(slot['when'])} "
        f"con {slot['doctor']}. Para cambiarla llame al 910 000 000."
    )


def masked_phone(phone: str | None) -> str:
    """`600123456` → `acaba en 456`: the only thing reception may say about a number on file."""
    return f"acaba en {patients.last_digits(phone)}"


def normalise_phone(said: str | None) -> str:
    """The digits of a number the caller read out, or "": `689 00 01 11` is `689000111`."""
    digits = "".join(character for character in (said or "") if character.isdigit())
    return digits if len(digits) == patients.PHONE_DIGITS else ""


def spoken_phone(phone: str) -> str:
    """`689000111` → `689 000 111`: a number grouped so a TTS reads it as a phone number."""
    return " ".join(phone[index : index + 3] for index in range(0, len(phone), 3))


def contact_confirmation_question(phone: str) -> str:
    """The sentence the caller has to say yes to before the clinic changes how it reaches them."""
    return f"Su nuevo teléfono de contacto sería el {spoken_phone(phone)}. ¿Se lo cambio?"


def appointment_line(appointment: dict[str, str]) -> str:
    """The cita as the stage that is about to cancel or confirm it reads it back."""
    return (
        f"Cita del paciente: {es.spanish_moment(appointment['when'])} con "
        f"{appointment['doctor']}"
        + (f" ({appointment['specialty']})" if appointment.get("specialty") else "")
        + ". Léesela —día, hora y profesional— y pregúntale si es esa."
    )


def cancellation_question(appointment: dict[str, str]) -> str:
    """The sentence a caller has to say yes to before the clinic gives their hour away."""
    return f"{es.spoken_moment(appointment['when'])} con {appointment['doctor']}, ¿se la anulo?"


def confirmation_question(slot: dict[str, str]) -> str:
    """The sentence the caller has to say yes to, rendered by us and never by the model."""
    return f"{es.spoken_moment(slot['when'])} con {slot['doctor']}, ¿lo confirmo?"


def new_confirmation_question(slot: dict[str, str]) -> str:
    """The sentence a caller with no cita has to say yes to before one is written for them."""
    return f"{es.spoken_moment(slot['when'])} con {slot['doctor']}, ¿se la reservo?"


def _offer(day: datetime.date, slots: list[dict[str, str]]) -> str:
    """The two hours to offer, or a plain 'no hay' for that day."""
    if not slots:
        return f"Sin huecos libres el {es.spanish_day(day)}."
    lines = [f"- {es.spanish_moment(s['when'])}, {s['doctor']}" for s in slots[:OFFER_LIMIT]]
    text = f"Huecos libres el {es.spanish_day(day)}:\n" + "\n".join(lines)
    return f"{text}\n{messages.MORE_LEFT}" if len(slots) > OFFER_LIMIT else text
