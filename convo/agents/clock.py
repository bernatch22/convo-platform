"""What day and time it is, for the model — a clock reading per session, a clock as a tool.

Decisions: docs/decisions/convo.agents.clock.md
"""

from datetime import date, datetime, time

from livekit.agents.llm import ChatItem, FunctionCall, FunctionCallOutput

from convo.domain.catalog import CLOCK
from convo.lang.es import DAY_NAMES as WEEKDAYS
from convo.lang.es import MONTH_NAMES as MONTHS

CLOCK_TOOL = CLOCK.name  # TenantAgent's clock; the reading below quotes it
CLOCK_CALL_ID = "lk_session_date"  # no dots: Anthropic's tool_use.id is ^[a-zA-Z0-9_-]+$


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


def clock_reading(today: date, now: time | None = None) -> list[ChatItem]:
    """The session's own reading of the clock, as the model sees any tool it called."""
    return [
        FunctionCall(call_id=CLOCK_CALL_ID, name=CLOCK_TOOL, arguments="{}"),
        FunctionCallOutput(
            call_id=CLOCK_CALL_ID,
            name=CLOCK_TOOL,
            output=date_note(today, now),
            is_error=False,
        ),
    ]
