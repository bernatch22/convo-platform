"""What Clínica Norte's reception can be wrong about, and what its calls may know.

The machinery — extract, match, escalate the remainder — is
`core.testing.grounding`, shared by every tenant. What lives here is the half
that is a clinic: an hour said the way a receptionist says it, a professional's
title, a street, and the clinic's own information sheet as the first source of
every answer.

Two functions are the whole contract with the platform: `stated_data(turns)`
and `evidence_of(turns)`. `evals/dag.py` hands them to the graph builder and
`tests/test_grounding.py` asserts on them directly, which is why every rule
below is a unit test that costs nothing to run.
"""

import re

from convo.lang import es
from convo.testing.metrics import grounding

from ..project import PROJECT

HOUR = "hora"
PRICE = "precio"
PERSON = "profesional"
PHONE = "teléfono"
ADDRESS = "dirección"

PROFESSIONAL = re.compile(
    r"\b(?:Dra|Dr|Sra|Sr|Dña|D)\.\s*"
    r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+)*"
)
STREET = re.compile(
    r"\b(?:calle|c/|avenida|avda\.?|paseo|plaza)\s+"
    r"[\wÁÉÍÓÚÑáéíóúñ]+(?:\s+[\wÁÉÍÓÚÑáéíóúñ0-9]+){0,3}",
    re.IGNORECASE,
)
# Only a spoken hour that names its part of the day: that is the shape the platform
# itself produces (`es.spoken_moment` always appends one), and without the suffix
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
    "madrugada": range(0, es.MORNING),
    "mañana": range(es.MORNING, es.AFTERNOON),
    "tarde": range(es.AFTERNOON, es.NIGHT),
    "noche": range(es.NIGHT, 24),
}


def spoken_hours(match: re.Match) -> tuple[str, ...]:
    """`las once de la mañana` becomes ('11:00',): the part of the day settles the ambiguity."""
    twelve = es.NUMBERS.index(match.group(1).lower())
    minute = MINUTES.get((match.group(2) or "").lower(), 0)
    if match.group(2) and match.group(2).isdigit():
        minute = int(match.group(2))
    window = PARTS[_part_of_day(match.group(3))]
    candidates = sorted({twelve % 24, (twelve + 12) % 24})
    return tuple(grounding.clock(hour, minute) for hour in candidates if hour in window)


EXTRACTORS = (
    grounding.clock_hours(HOUR),
    grounding.Extractor(HOUR, SPOKEN_HOUR, spoken_hours, grounding.HOURS),
    grounding.prices(PRICE),
    grounding.vocabulary(PERSON, PROFESSIONAL),
    grounding.phones(PHONE),
    grounding.vocabulary(ADDRESS, STREET),
)


def stated_data(turns: list) -> list[grounding.Datum]:
    """Every hour, price, professional, phone and address the receptionist stated."""
    return grounding.stated_data(turns, EXTRACTORS)


def evidence_of(turns: list) -> grounding.Evidence:
    """The clinic's sheet, what the patient said, and every tool output of the call."""
    return grounding.evidence_of(turns, PROJECT.knowledge_seed)


def unsupported(data: list[grounding.Datum], evidence: grounding.Evidence):
    """The data no source in the call accounts for — what is worth asking a judge about."""
    return grounding.unsupported(data, evidence)


def _part_of_day(word: str) -> str:
    """The part-of-day key as `PARTS` spells it, whatever case the agent used."""
    lowered = word.lower()
    return "mañana" if grounding.flatten(lowered) == "manana" else lowered
