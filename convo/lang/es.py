"""Spanish calendar words: what a caller says, what the agent says, and the date between them.

Pure functions that take the day as an argument, so every rule is a one-line
unit test. Today's date never reaches the model (docs/decisions/001).
"""

import datetime
import re
import unicodedata

DAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}
NEXT_WEEK_PHRASES = (
    "semana que viene",
    "proxima semana",
    "semana proxima",
    "semana siguiente",
    "siguiente semana",
)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
MONDAY = 0
HALF = 30
MORNING = 6
AFTERNOON = 13
NIGHT = 21
NUMBERS = (
    "",
    "una",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
    "diez",
    "once",
    "doce",
)


def resolve(text: str, today: datetime.date) -> datetime.date:
    """The date a caller means by `text` ("el jueves", "mañana", "la semana que viene")."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty date expression")
    if ISO_DATE.fullmatch(raw):
        return datetime.date.fromisoformat(raw)
    words = _normalise(raw)
    if "pasado manana" in words:
        return today + datetime.timedelta(days=2)
    if "manana" in words:
        return today + datetime.timedelta(days=1)
    if "hoy" in words:
        return today
    next_week = any(phrase in words for phrase in NEXT_WEEK_PHRASES)
    weekday = _weekday(words)
    if weekday is not None:
        return _in_next_week(today, weekday) if next_week else _upcoming(today, weekday)
    if next_week:
        return _monday_of_next_week(today)
    raise ValueError(f"unreadable date expression: {text!r}")


def spanish_day(value: datetime.date) -> str:
    """`jueves 3 de septiembre`: how a receptionist names a day out loud."""
    return f"{DAY_NAMES[value.weekday()]} {value.day} de {MONTH_NAMES[value.month - 1]}"


def spanish_date(iso: str) -> str:
    """The same from a stored `2026-09-02`; empty when there is none."""
    if not iso:
        return ""
    return spanish_day(datetime.date.fromisoformat(iso))


def spanish_moment(when: str) -> str:
    """`jueves 3 de septiembre a las 10:30` from an ISO timestamp, the clock form."""
    moment = datetime.datetime.fromisoformat(when)
    return f"{spanish_day(moment.date())} a las {moment:%H:%M}"


def spoken_moment(when: str) -> str:
    """`martes 8 de septiembre a la una de la tarde`: the hour as a person says it, for the ear."""
    moment = datetime.datetime.fromisoformat(when)
    return f"{spanish_day(moment.date())} a {spanish_hour(moment.hour, moment.minute)}"


def spanish_hour(hour: int, minute: int = 0) -> str:
    """`la una de la tarde`, `las nueve y media de la mañana`: a 24h time said out loud."""
    twelve = hour % 12 or 12
    said = "la una" if twelve == 1 else f"las {NUMBERS[twelve]}"
    if minute:
        said += " y media" if minute == HALF else f" y {minute}"
    return f"{said} {_part_of_day(hour)}"


def _part_of_day(hour: int) -> str:
    """Spanish splits the day at meals, not at noon: 13:00 is already «de la tarde»."""
    if hour < MORNING:
        return "de la madrugada"
    if hour < AFTERNOON:
        return "de la mañana"
    if hour < NIGHT:
        return "de la tarde"
    return "de la noche"


def _normalise(text: str) -> str:
    """Lowercase, accent-free, punctuation-free: `El Jueves,` and `el jueves` become one thing."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    letters = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", letters).split())


def _weekday(words: str) -> int | None:
    """The first weekday named in the phrase, as Python's Monday-is-0 index."""
    found = [(words.find(name), index) for name, index in WEEKDAYS.items() if name in words]
    return min(found)[1] if found else None


def _upcoming(today: datetime.date, weekday: int) -> datetime.date:
    """The next `weekday` strictly after today: `el jueves` said on a Thursday is the next one."""
    ahead = (weekday - today.weekday()) % 7
    return today + datetime.timedelta(days=ahead or 7)


def _monday_of_next_week(today: datetime.date) -> datetime.date:
    """The Monday that opens the following calendar week."""
    return today + datetime.timedelta(days=7 - today.weekday())


def _in_next_week(today: datetime.date, weekday: int) -> datetime.date:
    """That weekday inside the following calendar week, not merely the next one to come."""
    return _monday_of_next_week(today) + datetime.timedelta(days=weekday - MONDAY)
