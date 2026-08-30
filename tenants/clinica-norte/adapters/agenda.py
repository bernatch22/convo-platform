"""FakeAgenda: Clínica Norte's appointment book, invented but never random.

It stands where the clinic's real booking system will stand, and it answers the
same shape: a capability name, a dict of arguments, a list of plain slots. The
slots are drawn from a seeded generator keyed by day and specialty, so the same
question always gets the same answer — a test can assert on an hour, and a demo
run twice tells the same story.

Open source note: this file is the template a customer copies. Replace the
generator with an HTTP call to your own agenda, keep `capabilities()` and the
`{id, when, doctor}` shape, and every layer above (tool, guard, executor,
prompt) works unchanged. Two rules the port must keep: `when` is an ISO
timestamp, never a phrase in a language — the project turns it into words — and
an argument the system cannot read raises `ValueError`, which the executor
turns into a sentence the caller hears.
"""

import datetime
import random
import re
import unicodedata
from typing import Any

from core.adapters.base import Adapter

FIND_AVAILABILITY = "find_availability"
MAX_SLOTS = 3
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
SLOT_MINUTES = 30

WEEKDAY_HOURS = (8.5, 19.5)  # Monday to Friday, 8:30 to 19:30
SATURDAY_HOURS = (9.0, 13.5)  # Saturday morning only; Sunday the clinic is closed
SATURDAY = 5
SUNDAY = 6

# The cuadro médico as the booking system knows it. Keys are accent-free and
# lowercase; a specialty the caller words differently ("traumatólogo") matches
# on its first six characters, which is enough to tell Spanish specialties apart.
DOCTORS: dict[str, tuple[str, ...]] = {
    "medicina de familia": ("Dra. Marta Ruiz", "Dr. Javier Molina", "Dra. Lucia Serrano"),
    "pediatria": ("Dr. Pablo Iglesias", "Dra. Ana Belen Castro"),
    "ginecologia": ("Dra. Carmen Ortega", "Dr. Sergio Vidal"),
    "traumatologia": ("Dr. Alberto Navarro", "Dra. Irene Campos", "Dr. Hugo Ferrer"),
    "fisioterapia": ("Sr. Nacho Robles", "Sra. Eva Duran"),
    "reumatologia": ("Dra. Elena Prieto",),
    "cardiologia": ("Dr. Ramon Gil", "Dra. Beatriz Lara"),
    "neumologia": ("Dr. Tomas Vega",),
    "endocrinologia": ("Dra. Nuria Sanz",),
    "dermatologia": ("Dra. Sofia Lombardo",),
    "oftalmologia": ("Dr. Iñigo Salas",),
    "otorrinolaringologia": ("Dra. Patricia Nuñez",),
    "alergologia": ("Dr. Marcos Peña",),
    "psicologia": ("Dña. Laura Benito", "D. Andres Coll"),
    "psiquiatria": ("Dr. Fernando Aranda",),
    "neurologia": ("Dra. Rocio Mena",),
    "radiologia": ("Dr. Equipo de radiologia",),
}
ALIASES = {"medico de familia": "medicina de familia", "familia": "medicina de familia"}
DEFAULT_DOCTORS = ("Dra. Marta Ruiz", "Dr. Javier Molina", "Dra. Lucia Serrano")
KEY_PREFIX = 6


class FakeAgenda(Adapter):
    """The clinic's appointment book: which hours are free on a day, for a specialty."""

    def __init__(self, seed: str = "clinica-norte") -> None:
        self.seed = seed

    def capabilities(self) -> list[str]:
        """Reading availability is all this agenda does; booking arrives with ms-3."""
        return [FIND_AVAILABILITY]

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        """Run one capability against the book; ValueError on anything it cannot read."""
        if capability != FIND_AVAILABILITY:
            raise ValueError(f"FakeAgenda cannot run {capability!r}")
        return self.find_availability(args.get("date"), args.get("specialty"))

    def find_availability(self, day: Any, specialty: Any = None) -> list[dict[str, str]]:
        """Up to three free slots on `day` (YYYY-MM-DD), for a specialty when one is named.

        A closed day (Sunday) legitimately has none: an empty list is an answer,
        not a failure, and the receptionist says so and offers another day.
        """
        value = _parse_day(day)
        hours = _opening_hours(value)
        if not hours:
            return []
        key = _specialty_key(specialty)
        rng = random.Random(f"{self.seed}|{value.isoformat()}|{key}")
        times = sorted(rng.sample(hours, min(MAX_SLOTS, len(hours))))
        roster = _roster(rng, DOCTORS.get(key, DEFAULT_DOCTORS))
        return [self._slot(value, time, roster[n], key) for n, time in enumerate(times)]

    def _slot(
        self, day: datetime.date, time: datetime.time, doctor: str, key: str
    ) -> dict[str, str]:
        return {
            "id": f"sl-{day:%Y%m%d}-{time:%H%M}-{key[:4]}",
            "when": f"{day.isoformat()}T{time:%H:%M}",
            "doctor": doctor,
        }


def _parse_day(value: Any) -> datetime.date:
    """The day as a date, or ValueError — the executor turns that into a spoken sentence."""
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value.strip()):
        raise ValueError(f"find_availability needs a date as YYYY-MM-DD, got {value!r}")
    return datetime.date.fromisoformat(value.strip())


def _opening_hours(day: datetime.date) -> list[datetime.time]:
    """Every half hour the clinic is open that day; empty on Sundays."""
    if day.weekday() == SUNDAY:
        return []
    first, last = SATURDAY_HOURS if day.weekday() == SATURDAY else WEEKDAY_HOURS
    steps = int((last - first) * 60 // SLOT_MINUTES)
    start = datetime.datetime.combine(day, datetime.time()) + datetime.timedelta(hours=first)
    return [(start + datetime.timedelta(minutes=SLOT_MINUTES * n)).time() for n in range(steps + 1)]


def _specialty_key(specialty: Any) -> str:
    """The cuadro médico entry a caller's words point at, or `general` when none does."""
    if not isinstance(specialty, str) or not specialty.strip():
        return "general"
    words = _normalise(specialty)
    if words in ALIASES:
        return ALIASES[words]
    for name in DOCTORS:
        if name in words or words[:KEY_PREFIX] == name[:KEY_PREFIX]:
            return name
    return "general"


def _roster(rng: random.Random, doctors: tuple[str, ...]) -> list[str]:
    """One doctor per slot, shuffled and cycled: a small specialty repeats, a large one does not."""
    shuffled = list(doctors)
    rng.shuffle(shuffled)
    return [shuffled[n % len(shuffled)] for n in range(MAX_SLOTS)]


def _normalise(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    letters = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", letters).split())
