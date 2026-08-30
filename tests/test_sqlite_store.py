"""SQLiteStore: a session round-trips, and the events table cannot be edited."""

import sqlite3

import pytest

from core.state.events import Event
from core.state.store import SessionRow, SQLiteStore

pytestmark = pytest.mark.unit


@pytest.fixture
def store(tmp_path):
    return SQLiteStore(tmp_path / "convo.db")


def test_a_session_and_its_events_round_trip(store: SQLiteStore) -> None:
    store.open_session(SessionRow("s1", "clinica-norte", "reagendamiento", "chat", 1000.0))
    store.append("s1", Event(1, "session.start", 0, {"channel": "chat"}))
    store.append(
        "s1",
        Event(2, "tool.call", 40, {"tool": "find_availability", "args": {"phone": "60*******"}}),
    )
    store.close_session("s1", "completed", {"duration": 12.5})

    row = store.session("s1")
    assert row is not None and row.outcome == "completed" and row.report == {"duration": 12.5}
    assert row.event_count == 2
    assert [e.kind for e in store.events("s1")] == ["session.start", "tool.call"]
    assert store.events("s1")[1].payload["args"] == {"phone": "60*******"}
    assert [r.id for r in store.sessions()] == ["s1"]


def test_events_refuse_update_and_delete(store: SQLiteStore) -> None:
    store.open_session(SessionRow("s1", "t", "p", "chat", 1.0))
    store.append("s1", Event(1, "session.start", 0))

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("UPDATE events SET kind='edited' WHERE session_id='s1'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("DELETE FROM events WHERE session_id='s1'")


def test_a_duplicate_seq_is_refused(store: SQLiteStore) -> None:
    store.open_session(SessionRow("s1", "t", "p", "chat", 1.0))
    store.append("s1", Event(1, "session.start", 0))

    with pytest.raises(sqlite3.IntegrityError):
        store.append("s1", Event(1, "again", 5))
