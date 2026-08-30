"""`python -m convo sessions`: what an operator sees on stdout."""

import pytest

from convo import sessions
from core.state.events import Event
from core.state.store import MemoryStore, SessionRow

pytestmark = pytest.mark.unit


@pytest.fixture
def store() -> MemoryStore:
    store = MemoryStore()
    store.open_session(
        SessionRow("AJ_abc123", "clinica-norte", "reagendamiento", "chat", 1_700_000_000.0)
    )
    store.append("AJ_abc123", Event(1, "session.start", 0, {"channel": "chat"}))
    store.append(
        "AJ_abc123",
        Event(2, "tool.call", 812, {"tool": "find_patient", "args": {"phone": "60*******"}}),
    )
    store.append(
        "AJ_abc123",
        Event(
            3,
            "turn.agent",
            2210,
            {"text": "Buenos días", "metrics": {"llm_node_ttft": 0.41, "e2e_latency": 1.2}},
        ),
    )
    store.close_session("AJ_abc123", "completed", None)
    return store


def test_list_prints_one_line_per_session(store: MemoryStore, capsys) -> None:
    assert sessions.main(["list"], store) == 0
    out = capsys.readouterr().out
    assert "AJ_abc123" in out and "clinica-norte/reagendamiento" in out and "completed" in out
    assert out.rstrip().endswith("3")


def test_show_prints_the_seq_table_with_masked_pii_and_latencies(
    store: MemoryStore, capsys
) -> None:
    assert sessions.main(["show", "AJ_abc123"], store) == 0
    out = capsys.readouterr().out
    assert "   2     812  tool.call" in out
    assert "60*******" in out and "600123456" not in out
    assert "ttft=0.41s e2e=1.20s" in out


def test_show_of_an_unknown_session_says_so(store: MemoryStore, capsys) -> None:
    assert sessions.main(["show", "nope"], store) == 1
    assert "no session" in capsys.readouterr().out


def test_usage_on_anything_else(store: MemoryStore, capsys) -> None:
    assert sessions.main(["frobnicate"], store) == 2
