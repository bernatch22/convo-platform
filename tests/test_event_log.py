"""EventLog: seq counts from 1, time counts from the session start, nothing waits in a buffer."""

import pytest

from core.state.log import EventLog
from core.state.store import MemoryStore

pytestmark = pytest.mark.unit


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_seq_is_monotonic_and_t_ms_counts_from_the_session_start() -> None:
    clock, store = FakeClock(), MemoryStore()
    log = EventLog("s1", store, clock=clock)

    first = log.append("session.start")
    clock.now += 1.5
    second = log.append("tool.call", {"tool": "find_availability"})

    assert (first.seq, first.t_ms) == (1, 0)
    assert (second.seq, second.t_ms) == (2, 1500)


def test_append_writes_through_to_the_store_before_returning() -> None:
    store = MemoryStore()
    log = EventLog("s1", store)

    log.append("stage.enter", {"stage": "Identify"})

    assert [e.kind for e in store.events("s1")] == ["stage.enter"]
    assert log.events() == store.events("s1")
