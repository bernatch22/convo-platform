"""The board's arithmetic: irreversible calls counted off the log, by verb and by day.

The test that matters most here is the last one. A board that named the tools
it knows would need a deploy every time a project declared a new irreversible
write, and would quietly under-report the business in the meantime. So one
case runs a verb this codebase has never heard of, and one reads the module's
own source to prove no tool name is written into it.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convo.api.app import app, open_store
from convo.state import outcomes
from convo.state.events import Event
from convo.state.store import MemoryStore, SessionRow

pytestmark = pytest.mark.unit

TODAY = "sess-today"
YESTERDAY = "sess-yesterday"
BOOKED = "Cita movida al martes 3 a las 09:00 con la Dra. Ruiz."


def at(days_ago: int, hour: int = 10) -> float:
    """A wall-clock instant in the box's own timezone, so a day bucket is predictable."""
    day = datetime.now().date() - timedelta(days=days_ago)
    return datetime.combine(day, datetime.min.time()).replace(hour=hour).timestamp()


def seeded() -> MemoryStore:
    """Two clinic calls and one shop call: three transactions over two days, one of them failed."""
    store = MemoryStore()

    store.open_session(
        SessionRow(TODAY, "clinica-norte", "reagendamiento", "voice", started_at=at(0))
    )
    store.append(TODAY, Event(1, "session.start", 0, {"tenant": "clinica-norte"}))
    store.append(TODAY, Event(2, "confirm.granted", 1000, {"tool": "book_slot"}))
    store.append(
        TODAY, Event(3, "tool.call", 1200, {"tool": "book_slot", "side_effect": "irreversible"})
    )
    store.append(
        TODAY,
        Event(4, "tool.result", 1900, {"tool": "book_slot", "shape": "dict[3]", "summary": BOOKED}),
    )
    store.append(TODAY, Event(5, "session.end", 5000, {"outcome": "completed"}))
    store.close_session(TODAY, "completed", None)

    store.open_session(
        SessionRow(YESTERDAY, "clinica-norte", "reagendamiento", "voice", started_at=at(1))
    )
    # No grant before this one, and the adapter blew up: an unconfirmed, failed transaction.
    store.append(
        YESTERDAY,
        Event(1, "tool.call", 800, {"tool": "book_slot", "side_effect": "irreversible"}),
    )
    store.append(YESTERDAY, Event(2, "tool.error", 900, {"tool": "book_slot", "key": "timeout"}))
    store.close_session(YESTERDAY, "error", None)

    store.open_session(SessionRow("sess-shop", "tienda-sur", "pedidos", "chat", started_at=at(0)))
    store.append("sess-shop", Event(1, "confirm.granted", 500, {"tool": "cancel_order"}))
    store.append(
        "sess-shop",
        Event(2, "tool.call", 600, {"tool": "cancel_order", "side_effect": "irreversible"}),
    )
    # A read in the same call must never become a transaction.
    store.append(
        "sess-shop", Event(3, "tool.call", 700, {"tool": "find_order", "side_effect": "read"})
    )
    store.append("sess-shop", Event(4, "tool.result", 800, {"tool": "cancel_order"}))
    store.close_session("sess-shop", "completed", None)

    return store


@pytest.fixture
def store() -> MemoryStore:
    return seeded()


@pytest.fixture
def client(store: MemoryStore) -> TestClient:
    app.dependency_overrides[open_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_only_irreversible_calls_are_transactions(store) -> None:
    board = outcomes.outcomes(store)

    assert board["totals"]["transactions"] == 3, "the read in the shop call is not a transaction"
    assert [row["verb"] for row in board["rows"]].count("find_order") == 0


def test_each_verb_is_counted_with_its_consent_and_its_failures(store) -> None:
    board = outcomes.outcomes(store, tenant="clinica-norte", project="reagendamiento")

    assert board["verbs"] == [
        {"verb": "book_slot", "count": 2, "confirmed": 1, "failed": 1, "pending": 0}
    ]
    assert board["totals"] == {
        "transactions": 2,
        "confirmed": 1,
        "failed": 1,
        "sessions": 2,
    }


def test_the_days_strip_has_one_bucket_per_day_of_the_window(store) -> None:
    board = outcomes.outcomes(store, days=7)

    assert len(board["series"]) == 7, "empty days are bars of zero, not gaps"
    assert board["series"][-1]["day"] == datetime.now().date().isoformat()
    assert board["series"][-1]["verbs"] == {"book_slot": 1, "cancel_order": 1}
    assert board["series"][-2]["total"] == 1


def test_a_window_that_ends_before_a_transaction_does_not_count_it(store) -> None:
    board = outcomes.outcomes(store, days=1)

    assert board["totals"]["transactions"] == 2, "yesterday's booking is outside a one-day window"


def test_a_row_carries_its_session_and_the_summary_the_log_already_held(store) -> None:
    board = outcomes.outcomes(store, project="reagendamiento")
    done = next(row for row in board["rows"] if row["status"] == "done")

    assert (done["session"], done["tenant"], done["project"]) == (
        TODAY,
        "clinica-norte",
        "reagendamiento",
    )
    assert done["summary"] == BOOKED, "reused verbatim, never re-rendered"
    assert done["confirmed"] is True and done["seq"] == 3


def test_a_failed_call_keeps_no_summary_and_says_it_was_never_confirmed(store) -> None:
    board = outcomes.outcomes(store, project="reagendamiento")
    broken = next(row for row in board["rows"] if row["status"] == "failed")

    assert broken["summary"] is None and broken["confirmed"] is False


def test_a_call_still_running_leaves_its_transaction_pending(store) -> None:
    store.open_session(SessionRow("sess-live", "clinica-norte", "reagendamiento", "voice", at(0)))
    store.append(
        "sess-live",
        Event(1, "tool.call", 100, {"tool": "book_slot", "side_effect": "irreversible"}),
    )

    pending = outcomes.outcomes(store, project="reagendamiento")["verbs"][0]["pending"]

    assert pending == 1, "the result has not landed; the board must not call it done"


def test_rows_are_newest_first_and_obey_the_limit(store) -> None:
    board = outcomes.outcomes(store, limit=2)

    assert len(board["rows"]) == 2
    assert board["rows"][0]["at"] >= board["rows"][1]["at"]


# ── criterion 3: a tool nobody here has heard of ────────────────────────────


def test_a_brand_new_irreversible_tool_appears_with_no_board_code_changed(store) -> None:
    """The whole point: `create_appointment` is a string this codebase never declares."""
    store.open_session(
        SessionRow("sess-new", "clinica-norte", "reagendamiento", "voice", started_at=at(0))
    )
    store.append("sess-new", Event(1, "confirm.granted", 400, {"tool": "create_appointment"}))
    store.append(
        "sess-new",
        Event(2, "tool.call", 500, {"tool": "create_appointment", "side_effect": "irreversible"}),
    )
    store.append(
        "sess-new",
        Event(3, "tool.result", 900, {"tool": "create_appointment", "summary": "Cita creada."}),
    )

    board = outcomes.outcomes(store, project="reagendamiento")
    verbs = {tally["verb"]: tally for tally in board["verbs"]}

    assert verbs["create_appointment"]["count"] == 1
    assert verbs["create_appointment"]["confirmed"] == 1
    assert board["series"][-1]["verbs"]["create_appointment"] == 1
    assert any(row["summary"] == "Cita creada." for row in board["rows"])


def test_the_module_names_no_tool_at_all(store) -> None:
    """Pinned by reading the source: the aggregation keys on side_effect, never on a list."""
    source = Path(outcomes.__file__).read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    body = code.split('"""', 2)[-1]  # past the module docstring, which may discuss examples

    for tool in ("book_slot", "cancel_order", "create_appointment", "cancel_slot", "send_sms"):
        assert tool not in body, f"{tool} is hardcoded in core/outcomes.py"


# ── the door ────────────────────────────────────────────────────────────────


def test_the_endpoint_narrows_to_one_project_and_refuses_a_silly_window(client) -> None:
    board = client.get("/outcomes?tenant=tienda-sur&project=pedidos&days=7").json()

    assert [tally["verb"] for tally in board["verbs"]] == ["cancel_order"]
    assert board["rows"][0]["session"] == "sess-shop"
    assert client.get("/outcomes?days=0").status_code == 422
    assert client.get(f"/outcomes?days={outcomes.MAX_DAYS + 1}").status_code == 422


def test_the_window_is_reported_back_so_the_screen_can_label_itself(client) -> None:
    board = client.get("/outcomes?days=3").json()

    assert board["days"] == 3
    assert board["until"] <= time.time() + 1
    assert board["since"] < board["until"]
