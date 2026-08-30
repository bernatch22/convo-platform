"""The shop's calendar words: an ISO date as a person says it out loud.

The order system stores `2026-09-02`; a customer hears "el miércoles 2 de
septiembre". Turning one into the other is not the model's job — a date read
back wrong is a delivery day promised wrong — so the platform renders it and
the model reads what it is given.

Pure functions that take the date as an argument: no clock, no context, no I/O,
which is why every rule below is a one-line unit test.

Open source note: this is the one place where two tenants of this repo hold
almost the same file. Spanish calendar words are not a clinic's or a shop's
property, and a small `es` formatting package upstream would delete both — but
sharing them through one tenant importing another would tie two customers'
deploys together, which is worse than a duplicated month list.
"""

import datetime

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


def spanish_day(value: datetime.date) -> str:
    """`miércoles 2 de septiembre` — how the order desk names a day out loud."""
    return f"{DAY_NAMES[value.weekday()]} {value.day} de {MONTH_NAMES[value.month - 1]}"


def spanish_date(iso: str) -> str:
    """The same, from the `2026-09-02` the order system stores; empty when there is none."""
    if not iso:
        return ""
    return spanish_day(datetime.date.fromisoformat(iso))
