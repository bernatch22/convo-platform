"""The clinic's calendar rules: who consults, when the doors are open, which hours are free.

Decisions: docs/decisions/tenants.clinica-norte.adapters.slots.md
"""

import datetime
import random
import re
import unicodedata

MAX_SLOTS = 3
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

SLOT_ID = re.compile(r"sl-(\d{8})-(\d{4})-[a-z0-9]+")


def free_slots(seed: str, day: datetime.date, specialty: str | None = None) -> list[dict[str, str]]:
    """Up to three free `{id, when, doctor}` on `day`; a closed day legitimately has none."""
    hours = opening_hours(day)
    if not hours:
        return []
    key = specialty_key(specialty)
    rng = random.Random(f"{seed}|{day.isoformat()}|{key}")
    times = sorted(rng.sample(hours, min(MAX_SLOTS, len(hours))))
    roster = _roster(rng, DOCTORS.get(key, DEFAULT_DOCTORS))
    return [
        {"id": slot_id(day, time, key), "when": f"{day.isoformat()}T{time:%H:%M}", "doctor": doctor}
        for time, doctor in zip(times, roster, strict=False)
    ]


def opening_hours(day: datetime.date) -> list[datetime.time]:
    """Every half hour the clinic is open that day; empty on Sundays."""
    if day.weekday() == SUNDAY:
        return []
    first, last = SATURDAY_HOURS if day.weekday() == SATURDAY else WEEKDAY_HOURS
    steps = int((last - first) * 60 // SLOT_MINUTES)
    start = datetime.datetime.combine(day, datetime.time()) + datetime.timedelta(hours=first)
    return [(start + datetime.timedelta(minutes=SLOT_MINUTES * n)).time() for n in range(steps + 1)]


def slot_id(day: datetime.date, time: datetime.time, key: str) -> str:
    """`sl-20260903-1100-trau` — the handle the booking system books against."""
    return f"sl-{day:%Y%m%d}-{time:%H%M}-{key[:4]}"


def moment_of(identifier: str) -> str:
    """The ISO timestamp an id stands for, or ValueError when the id is not one of ours."""
    match = SLOT_ID.fullmatch(identifier.strip() if isinstance(identifier, str) else "")
    if not match:
        raise ValueError(f"not a slot id: {identifier!r}")
    date, time = match.group(1), match.group(2)
    return f"{date[:4]}-{date[4:6]}-{date[6:]}T{time[:2]}:{time[2:]}"


def specialty_key(specialty: str | None) -> str:
    """The cuadro médico entry a caller's words point at, or `general` when none does."""
    if not isinstance(specialty, str) or not specialty.strip():
        return "general"
    words = normalise(specialty)
    if words in ALIASES:
        return ALIASES[words]
    for name in DOCTORS:
        if name in words or words[:KEY_PREFIX] == name[:KEY_PREFIX]:
            return name
    return "general"


def normalise(text: str) -> str:
    """Lowercase, accent-free, punctuation-free: `Traumatología,` and `traumatologia` are one."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    letters = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", letters).split())


def _roster(rng: random.Random, doctors: tuple[str, ...]) -> list[str]:
    """One doctor per slot, shuffled and cycled: a small specialty repeats, a large one does not."""
    shuffled = list(doctors)
    rng.shuffle(shuffled)
    return [shuffled[n % len(shuffled)] for n in range(MAX_SLOTS)]
