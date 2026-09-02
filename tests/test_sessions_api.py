"""The read side: the session list, one session in full, and the live SSE stream of its log."""

import json

import pytest
from fastapi.testclient import TestClient

from convo.api import client as control_plane
from convo.api.app import app, open_store
from convo.state.events import Event
from convo.state.store import MemoryStore, SessionRow

pytestmark = pytest.mark.unit

FINISHED = "sess-finished"
RUNNING = "sess-running"


def seeded() -> MemoryStore:
    """Two sessions: one voice call that ended and was priced, one chat still running."""
    store = MemoryStore()
    store.open_session(
        SessionRow(FINISHED, "clinica-norte", "reagendamiento", "voice", started_at=200.0)
    )
    store.append(FINISHED, Event(1, "session.start", 0, {"tenant": "clinica-norte"}))
    store.append(FINISHED, Event(2, "turn.user", 900, {"text": "hola"}))
    store.append(FINISHED, Event(3, "turn.agent", 1800, {"text": "buenas", "metrics": {}}))
    store.append(
        FINISHED, Event(4, "session.end", 4000, {"outcome": "completed", "cost": {"eur": 0.0031}})
    )
    store.close_session(FINISHED, "completed", {"duration": 4.0})
    store.open_session(SessionRow(RUNNING, "tienda-sur", "pedidos", "chat", started_at=100.0))
    store.append(RUNNING, Event(1, "session.start", 0, {"tenant": "tienda-sur"}))
    store.append(RUNNING, Event(2, "turn.user", 500, {"text": "¿dónde está mi pedido?"}))
    return store


@pytest.fixture
def store() -> MemoryStore:
    return seeded()


@pytest.fixture
def client(store: MemoryStore) -> TestClient:
    app.dependency_overrides[open_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_list_is_newest_first_with_the_numbers_the_console_shows(client) -> None:
    rows = client.get("/sessions").json()

    assert [row["id"] for row in rows] == [FINISHED, RUNNING], "newest session first"
    finished = rows[0]
    assert (finished["tenant"], finished["project"]) == ("clinica-norte", "reagendamiento")
    assert (finished["events"], finished["turns"]) == (4, 2)
    assert finished["cost_eur"] == 0.0031 and finished["outcome"] == "completed"


def test_a_running_session_has_no_outcome_and_no_price_yet(client) -> None:
    running = next(row for row in client.get("/sessions").json() if row["id"] == RUNNING)

    assert running["outcome"] is None and running["cost_eur"] is None


def test_the_list_narrows_to_one_tenant_and_obeys_the_limit(client) -> None:
    assert [r["id"] for r in client.get("/sessions?tenant=tienda-sur").json()] == [RUNNING]
    assert len(client.get("/sessions?limit=1").json()) == 1
    assert client.get("/sessions?limit=0").status_code == 422, "a limit of zero is nonsense"


def test_one_session_carries_every_event_in_seq_order_and_its_report(client) -> None:
    view = client.get(f"/sessions/{FINISHED}").json()

    assert [e["seq"] for e in view["events"]] == [1, 2, 3, 4]
    assert view["events"][1] == {
        "seq": 2,
        "t_ms": 900,
        "kind": "turn.user",
        "payload": {"text": "hola"},
    }
    assert view["report"] == {"duration": 4.0}


def test_an_unknown_session_is_a_404(client) -> None:
    reply = client.get("/sessions/nope")

    assert reply.status_code == 404 and "nope" in reply.json()["detail"]


def test_the_live_stream_replays_the_log_and_closes_on_the_end_event(client) -> None:
    with client.stream("GET", f"/sessions/{FINISHED}/live") as reply:
        assert reply.headers["content-type"].startswith("text/event-stream")
        frames = list(_frames(reply, stop_at="end"))

    names = [name for name, _ in frames]
    assert names == ["open", "append", "append", "append", "append", "end"]
    assert dict(frames)["open"]["id"] == FINISHED
    assert dict(frames)["end"]["outcome"] == "completed"


async def test_a_client_may_start_from_a_cursor_and_walk_away_mid_stream(store) -> None:
    """A live call has no end frame to wait for, so the reader leaves when it has had enough.

    Read against the generator rather than through `TestClient`: the client
    blocks its portal until the response finishes, and the whole point of this
    stream is that it does not finish while the caller is still talking.
    """
    stream = control_plane.live(store, RUNNING, after=1)

    opened = _parse(await anext(stream))
    appended = _parse(await anext(stream))
    await stream.aclose()  # the browser closed the tab

    assert opened == ("open", RUNNING)
    assert appended[0] == "append" and appended[1] == 2, "?after=1 skips what the client had"


def test_the_live_stream_of_an_unknown_session_says_so_and_closes(client) -> None:
    with client.stream("GET", "/sessions/nope/live") as reply:
        frames = list(_frames(reply, stop_at="error"))

    assert frames == [("error", {"error": "no session nope"})]


def _frames(reply, stop_at: str | None = None, limit: int = 20):
    """Read `event:`/`data:` pairs off an SSE response until the named frame, or `limit`."""
    name = None
    seen = 0
    for line in reply.iter_lines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            yield name, json.loads(line.removeprefix("data: "))
            seen += 1
            if name == stop_at or seen >= limit:
                return


def _parse(frame: str) -> tuple[str, object]:
    """One SSE frame back into (event name, the id or seq it carries)."""
    name = frame.splitlines()[0].removeprefix("event: ")
    data = json.loads(frame.splitlines()[1].removeprefix("data: "))
    return name, data.get("seq", data.get("id"))
