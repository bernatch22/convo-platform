"""Which concrete facts a reply states: the patterns, the normalisers, the extraction pass.

Decisions: docs/decisions/convo.testing.metrics.grounding.extract.md
"""

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass

# Which index of the evidence a datum is looked up in. CALL is TEXT minus the knowledge
# block: a shop's information sheet names every carrier it works with, so the sheet grounds
# "lo lleva MRW" on a parcel SEUR is carrying. Claims about THIS call — a carrier, a
# reference, an amount charged — have to be found in what the call itself produced.
TEXT, HOURS, DIGITS, CALL = "text", "hours", "digits", "call"

# Lookarounds rather than \b: a row comes back as `2026-09-03T10:00`, and a word
# boundary between the `T` and the `1` does not exist — so the hour a caller was told
# had no source and a correct answer scored 0.0.
CLOCK = re.compile(r"(?<!\d)(\d{1,2})[:.](\d{2})(?!\d)")
PRICE_TAG = re.compile(r"\b(\d{1,4})\s*(?:€|euros?)\b", re.IGNORECASE)
PHONE_NUMBER = re.compile(r"\b\d{3}[ .\-]?\d{2,3}[ .\-]?\d{3,4}\b")


@dataclass(frozen=True)
class Datum:
    """One checkable thing the agent said, and the forms that would ground it."""

    kind: str
    said: str
    keys: tuple[str, ...]
    turn: int
    against: str = TEXT

    def __str__(self) -> str:
        return f"{self.kind}: «{self.said}» (turno {self.turn})"


@dataclass(frozen=True)
class Extractor:
    """One kind of claim a project can be wrong about: a pattern and the keys it grounds under."""

    kind: str
    pattern: re.Pattern
    keys: Callable[[re.Match], tuple[str, ...]]
    against: str = TEXT

    def data_in(self, text: str, turn: int) -> list[Datum]:
        """Every datum of this kind stated in one assistant message."""
        return [
            Datum(self.kind, m.group(0), self.keys(m), turn, self.against)
            for m in self.pattern.finditer(text)
        ]


def clock_hours(kind: str) -> Extractor:
    """`14:00` and `9.30`, matched against every hour the evidence contains."""
    return Extractor(kind, CLOCK, lambda m: (clock(int(m.group(1)), int(m.group(2))),), HOURS)


def prices(kind: str) -> Extractor:
    """`90 euros`, `74,90 €` — the amount as the agent said it."""
    return Extractor(kind, PRICE_TAG, lambda m: (f"{int(m.group(1))} euros",))


def phones(kind: str) -> Extractor:
    """A phone number, matched on digits alone: `910 000 000` and `910000000` are one."""
    return Extractor(kind, PHONE_NUMBER, lambda m: (digits(m.group(0)),), DIGITS)


def vocabulary(kind: str, pattern: re.Pattern, against: str = TEXT) -> Extractor:
    """A project's own words — a title, a street, a carrier — matched as flattened text."""
    return Extractor(kind, pattern, lambda m: (flatten(m.group(0)),), against)


def stated_data(turns: list, extractors: Iterable[Extractor]) -> list[Datum]:
    """Every concrete datum the agent stated, in the order it stated them, without repeats."""
    data: list[Datum] = []
    for index, turn in enumerate(turns):
        if getattr(turn, "role", None) == "assistant":
            for extractor in extractors:
                data.extend(extractor.data_in(turn.content or "", index))
    return _without_repeats(data)


def flatten(text: str) -> str:
    """Lowercase, accent-free, punctuation-free: `Dra. Sofía` and `dra sofia` become one."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    letters = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", letters).split())


def digits(text: str) -> str:
    """Only the digits, so `910 000 000` and `910000000` are the same phone number."""
    return re.sub(r"\D", "", text)


def clock(hour: int, minute: int) -> str:
    """`(9, 0)` becomes `09:00`, so a sheet writing `8:00` and a reply writing `08:00` match."""
    return f"{hour % 24:02d}:{minute:02d}"


def clock_hours_in(text: str) -> list[str]:
    """Every `HH:MM` in a block of evidence, zero-padded."""
    return [clock(int(m.group(1)), int(m.group(2))) for m in CLOCK.finditer(text)]


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
