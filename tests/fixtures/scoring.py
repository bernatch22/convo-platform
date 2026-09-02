"""Fixtures and fakes shared by the scoring tests."""

from convo.state.events import Event
from convo.state.store import MemoryStore, SessionRow

SESSION = "sess-scored"
TENANT, PROJECT = "clinica-norte", "reagendamiento"


def turn(seq: int, role: str, text: str, t_ms: int | None = None) -> Event:
    return Event(seq, f"turn.{role}", t_ms if t_ms is not None else seq * 100, {"text": text})


def call(seq: int, tool: str, effect: str = "irreversible") -> Event:
    return Event(seq, "tool.call", seq * 100, {"tool": tool, "side_effect": effect})


def granted(seq: int, tool: str) -> Event:
    return Event(seq, "confirm.granted", seq * 100, {"tool": tool, "audience": f"{tool}:ab"})


def good_call() -> list[Event]:
    """A short, correct clinic call: consent asked and granted before the one write."""
    return [
        Event(1, "session.start", 0, {"tenant": TENANT}),
        turn(2, "agent", "Clínica Norte, buenos días, le atiende recepción."),
        turn(3, "user", "quería cambiar mi cita"),
        turn(4, "agent", "Por supuesto, ¿me dice su nombre?"),
        turn(5, "user", "Marta Alonso"),
        granted(6, "book_slot"),
        call(7, "book_slot"),
        turn(8, "agent", "Hecho, queda el jueves a las once."),
        Event(9, "session.end", 900, {"outcome": "completed", "cost": {"eur": 0.003}}),
    ]


def stored(
    events: list[Event],
    closed: bool = True,
    project: str = PROJECT,
    started_at: float = 100.0,
) -> MemoryStore:
    store = MemoryStore()
    store.open_session(SessionRow(SESSION, TENANT, project, "voice", started_at=started_at))
    for event in events:
        store.append(SESSION, event)
    if closed:
        store.close_session(SESSION, "completed", None)
    return store


def turns_of(events: list[Event]) -> list:
    from convo.testing import replay

    return replay.turns_from(events)
