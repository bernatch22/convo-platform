"""Which concrete facts a reply states, and what in the call could possibly back them up.

The judge that used to answer "did the agent invent this?" could not see the
evidence, so it guessed, and it guessed differently on Tuesday than on
Wednesday: the price golden flipped between 0.0 and 0.9 across runs of the same
prompt. The fix is not a better-worded criterion. It is to stop asking a model
a question that code can answer.

Two halves, both pure functions with no model anywhere near them:

- `stated_data` pulls the concrete data out of what the AGENT said — clock
  hours, spoken hours, prices, professionals, phone numbers, addresses. Nothing
  else counts as a checkable fact: "las citas se pueden cambiar" is a policy,
  "90 euros" is a number somebody can be wrong about.
- `evidence_of` collects everything that could ground them: the clinic's own
  information sheet, what the caller said (a patient reading out their phone
  number is the source for the agent repeating it), and the output of every
  tool the turn ran. Deliberately NOT the agent's own earlier replies, which
  would let an invention launder itself one turn later.

Matching is exact after normalising: lowercase, accent-free, punctuation-free,
and hours compared as `HH:MM` so `8:00` in the sheet grounds `las ocho de la
mañana` on the phone. What survives that is not proof of an invention — it is
the short list worth paying a judge to look at, with the evidence attached.

Open source note: `stated_data` is the only Spanish-specific part (the spoken
hour and the professional titles). A project in another language rewrites two
regexes and keeps the shape: extract, match, escalate the remainder.
"""

import re
import unicodedata
from dataclasses import dataclass

from .. import dates
from ..knowledge import CLINIC

HOUR = "hora"
PRICE = "precio"
PERSON = "profesional"
PHONE = "teléfono"
ADDRESS = "dirección"

# Lookarounds rather than \b: an agenda row comes back as `2026-09-03T10:00`, and a word
# boundary between the `T` and the `1` does not exist — so the hour a patient was told
# on the phone had no source and a correct answer scored 0.0.
CLOCK = re.compile(r"(?<!\d)(\d{1,2})[:.](\d{2})(?!\d)")
PRICE_TAG = re.compile(r"\b(\d{1,4})\s*(?:€|euros?)\b", re.IGNORECASE)
PROFESSIONAL = re.compile(
    r"\b(?:Dra|Dr|Sra|Sr|Dña|D)\.\s*"
    r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+)*"
)
PHONE_NUMBER = re.compile(r"\b\d{3}[ .\-]?\d{2,3}[ .\-]?\d{3,4}\b")
STREET = re.compile(
    r"\b(?:calle|c/|avenida|avda\.?|paseo|plaza)\s+"
    r"[\wÁÉÍÓÚÑáéíóúñ]+(?:\s+[\wÁÉÍÓÚÑáéíóúñ0-9]+){0,3}",
    re.IGNORECASE,
)
# Only a spoken hour that names its part of the day: that is the shape the platform
# itself produces (`dates.spoken_moment` always appends one), and without the suffix
# "las dos" in "le ofrezco las dos horas" reads as two o'clock.
SPOKEN_HOUR = re.compile(
    r"\b(?:la|las)\s+(una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)"
    r"(?:\s+y\s+(media|cuarto|\d{1,2}))?"
    r"\s+de\s+la\s+(ma[ñn]ana|tarde|noche|madrugada)",
    re.IGNORECASE,
)

QUARTER, HALF = 15, 30
MINUTES = {"media": HALF, "cuarto": QUARTER}
PARTS = {
    "madrugada": range(0, dates.MORNING),
    "mañana": range(dates.MORNING, dates.AFTERNOON),
    "tarde": range(dates.AFTERNOON, dates.NIGHT),
    "noche": range(dates.NIGHT, 24),
}


@dataclass(frozen=True)
class Datum:
    """One checkable thing the agent said, and the forms that would ground it."""

    kind: str
    said: str
    keys: tuple[str, ...]
    turn: int

    def __str__(self) -> str:
        return f"{self.kind}: «{self.said}» (turno {self.turn})"


@dataclass(frozen=True)
class Evidence:
    """Everything the agent was entitled to state, flattened three ways for matching."""

    text: str
    hours: frozenset[str]
    digits: str

    def grounds(self, datum: Datum) -> bool:
        """Whether any of the datum's forms appears in the evidence."""
        if datum.kind == HOUR:
            return any(key in self.hours for key in datum.keys)
        if datum.kind == PHONE:
            return any(key in self.digits for key in datum.keys)
        return any(key in self.text for key in datum.keys)


def stated_data(turns: list) -> list[Datum]:
    """Every concrete datum the agent stated, in the order it stated them, without repeats."""
    data: list[Datum] = []
    for index, turn in enumerate(turns):
        if getattr(turn, "role", None) == "assistant":
            data.extend(_data_in(turn.content or "", index))
    return _without_repeats(data)


def evidence_of(turns: list) -> Evidence:
    """The clinic's sheet, what the caller said, and every tool output of the call."""
    parts = [CLINIC]
    for turn in turns:
        if getattr(turn, "role", None) == "user":
            parts.append(turn.content or "")
        for call in getattr(turn, "tools_called", None) or []:
            if call.output is not None:
                parts.append(str(call.output))
    raw = "\n".join(parts)
    return Evidence(text=flatten(raw), hours=frozenset(_clock_hours(raw)), digits=_digits(raw))


def unsupported(data: list[Datum], evidence: Evidence) -> list[Datum]:
    """The data no source in the call accounts for — what is worth asking a judge about."""
    return [datum for datum in data if not evidence.grounds(datum)]


def flatten(text: str) -> str:
    """Lowercase, accent-free, punctuation-free: `Dra. Sofía` and `dra sofia` become one."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    letters = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", letters).split())


def _data_in(text: str, turn: int) -> list[Datum]:
    """Every datum one assistant message states, one regex per kind of claim."""
    data = [
        Datum(HOUR, m.group(0), (_clock(int(m.group(1)), int(m.group(2))),), turn)
        for m in CLOCK.finditer(text)
    ]
    data += [Datum(HOUR, m.group(0), _spoken_hours(m), turn) for m in SPOKEN_HOUR.finditer(text)]
    data += [
        Datum(PRICE, m.group(0), (f"{int(m.group(1))} euros",), turn)
        for m in PRICE_TAG.finditer(text)
    ]
    data += [
        Datum(PERSON, m.group(0), (flatten(m.group(0)),), turn) for m in PROFESSIONAL.finditer(text)
    ]
    data += [
        Datum(PHONE, m.group(0), (_digits(m.group(0)),), turn) for m in PHONE_NUMBER.finditer(text)
    ]
    data += [
        Datum(ADDRESS, m.group(0), (flatten(m.group(0)),), turn) for m in STREET.finditer(text)
    ]
    return data


def _spoken_hours(match: re.Match) -> tuple[str, ...]:
    """`las once de la mañana` becomes ('11:00',): the part of the day settles the ambiguity."""
    twelve = dates.NUMBERS.index(match.group(1).lower())
    minute = MINUTES.get((match.group(2) or "").lower(), 0)
    if match.group(2) and match.group(2).isdigit():
        minute = int(match.group(2))
    window = PARTS[_flatten_part(match.group(3))]
    candidates = sorted({twelve % 24, (twelve + 12) % 24})
    return tuple(_clock(hour, minute) for hour in candidates if hour in window)


def _flatten_part(word: str) -> str:
    """The part-of-day key as `PARTS` spells it, whatever case the agent used."""
    lowered = word.lower()
    return "mañana" if flatten(lowered) == "manana" else lowered


def _clock(hour: int, minute: int) -> str:
    """`(9, 0)` becomes `09:00`, so a sheet writing `8:00` and a reply writing `08:00` match."""
    return f"{hour % 24:02d}:{minute:02d}"


def _clock_hours(text: str) -> list[str]:
    """Every `HH:MM` in a block of evidence, zero-padded."""
    return [_clock(int(m.group(1)), int(m.group(2))) for m in CLOCK.finditer(text)]


def _digits(text: str) -> str:
    """Only the digits, so `910 000 000` and `910000000` are the same phone number."""
    return re.sub(r"\D", "", text)


def _without_repeats(data: list[Datum]) -> list[Datum]:
    """One entry per (kind, keys): an agent repeating an hour states one fact, not two."""
    seen: set[tuple[str, tuple[str, ...]]] = set()
    unique = []
    for datum in data:
        key = (datum.kind, datum.keys)
        if key not in seen:
            seen.add(key)
            unique.append(datum)
    return unique
