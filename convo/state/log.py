"""EventLog: the append-only record of one session, numbered by `seq`, written as it happens.

Decisions: docs/decisions/convo.state.log.md
"""

import time
from collections.abc import Callable
from typing import Any

from convo.state.events import Event
from convo.state.store import Store
from convo.tools import guard

Clock = Callable[[], float]


class EventLog:
    """One session's log: `append` numbers the fact and writes it through to the store."""

    def __init__(self, session_id: str, store: Store, clock: Clock = time.monotonic) -> None:
        self.session_id = session_id
        self.store = store
        self.clock = clock
        self.started_at = clock()
        self.seq = 0

    def append(self, kind: str, payload: dict[str, Any] | None = None) -> Event:
        """Record one fact: next seq, ms since start, written before this returns."""
        self.seq += 1
        event = Event(seq=self.seq, kind=kind, t_ms=self._elapsed_ms(), payload=payload or {})
        self.store.append(self.session_id, event)
        return event

    def events(self) -> list[Event]:
        """Everything recorded so far, in seq order, read back from the store."""
        return self.store.events(self.session_id)

    def _elapsed_ms(self) -> int:
        return int((self.clock() - self.started_at) * 1000)


def record(tc: Any, kind: str, payload: dict[str, Any] | None = None) -> None:
    """Append one fact to a context's log, masked, for callers that may not have one."""
    if getattr(tc, "log", None) is not None:
        tc.log.append(kind, guard.scrub(payload or {}, getattr(tc, "pii_values", ())))
