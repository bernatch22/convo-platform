"""The tools the reagendamiento project puts in the model's hands.

A tool docstring here is not documentation for a developer: it is the schema
Claude reads before deciding whether to call, so it is written in Spanish, for
the model, and it says when to use the tool and exactly what to put in each
argument. The body stays thin — resolve the caller's words into a date, hand
the call to `tc.tools.call`, turn the result into a line the model can read
aloud — because guard, timeout, logging and failure sentences all live in the
platform's executor, never here.
"""

import datetime
from typing import Any

from core.agents import RunContext, ToolError, function_tool
from core.context import TenantContext

from . import dates

UNREADABLE_DATE = "No he entendido para qué día lo quiere. ¿Me dice el día de la semana o la fecha?"


@function_tool
async def find_availability(
    ctx: RunContext[TenantContext],
    date: str,
    specialty: str | None = None,
) -> str:
    """Consulta la agenda de la clínica y devuelve hasta tres huecos libres de un día.

    Llámala en cuanto el paciente nombre un día, aunque no sepas nada más de él:
    siempre que pregunte por disponibilidad, quiera cambiar una cita a otro día o
    mencione una fecha. Nunca digas que hay hueco, ni que no lo hay, sin haberla
    llamado antes: tú no ves la agenda, ella sí.

    Args:
        date: el día tal y como lo ha dicho el paciente, con sus mismas palabras
            ("el jueves", "mañana", "pasado mañana", "la semana que viene"), o en
            formato AAAA-MM-DD si ha dado una fecha exacta. No calcules tú la
            fecha ni preguntes qué día es hoy.
        specialty: la especialidad, solo si el paciente ya la ha dicho
            ("traumatología", "pediatría", "cardiología"). Omítela mientras no la
            sepas y no se la preguntes para poder llamar a esta herramienta: sin
            especialidad la agenda responde igual, con los huecos del centro.

    Devuelve un texto con hasta tres huecos (día, hora y profesional), o la
    indicación de que ese día no queda ninguno.
    """
    tc = ctx.userdata
    try:
        day = dates.resolve(date, tc.today)
    except ValueError:
        raise ToolError(UNREADABLE_DATE) from None
    args: dict[str, Any] = {"date": day.isoformat()}
    if specialty:
        args["specialty"] = specialty
    slots = await tc.tools.call("find_availability", args)
    return _offer(day, slots)


def _offer(day: datetime.date, slots: list[dict[str, str]]) -> str:
    """What the model reads back: one line per free slot, or a plain 'no hay' for that day.

    The agenda's slot id is deliberately left out. Everything in here is text a
    voice agent may read aloud, and `sl-20260903-1100-trau` is not a sentence;
    it comes back the day the model can actually book with it (ms-3).
    """
    if not slots:
        return f"Sin huecos libres el {dates.spanish_day(day)}."
    lines = [f"- {dates.spanish_moment(s['when'])}, {s['doctor']}" for s in slots]
    return f"Huecos libres el {dates.spanish_day(day)}:\n" + "\n".join(lines)
