"""What day and time it is, for the model — a static note for the date, a tool for the clock.

The system prompt must stay byte-identical or Haiku's cache is gone, so the
date cannot live there; the tools resolve "mañana" against `tc.today`, but a
patient asking "¿hoy qué día es?" is talking to the MODEL, and a model with
no calendar invents one (it said "viernes" on a Saturday, on a real call).
The note is written ONCE per session as a system item after the cached
prefix and carries ONLY the date: the day does not change mid-call, so it can
be static. The time of day can — a note with minutes would be stale before the
goodbye — so the clock is a TOOL (`TenantAgent.fecha_y_hora_actual`) the model
calls at the moment it is asked, recomputed every single time.

Open source note: Spanish only because both demo tenants speak it; a project
in another language overrides `Project.date_note` with its own renderer.
"""

from datetime import date, datetime, time

WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MONTHS = (
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


def date_note(today: date, now: time | None = None) -> str:
    """One prose line: 'Hoy es sábado 30 de agosto de 2026 y son las 21:39.'"""
    weekday, month = WEEKDAYS[today.weekday()], MONTHS[today.month - 1]
    day = f"Hoy es {weekday} {today.day} de {month} de {today.year}"
    if now is None:
        return f"{day}. (Contexto para ti: no lo anuncies salvo que te lo pregunten.)"
    return f"{day} y son las {now.hour}:{now.minute:02d}."


def current_note(today: date | None = None) -> str:
    """The note for this very moment, on the machine's clock."""
    moment = datetime.now()
    return date_note(today or moment.date(), moment.time())
