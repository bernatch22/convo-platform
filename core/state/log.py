"""EventLog: the append-only record of one session, numbered by `seq`, written as it happens.

Every fact worth auditing — a stage entered, a tool called, a yes granted, a
saga undone, a turn with its latencies — becomes one Event with the next
`seq` and a millisecond offset from the session start, and reaches the store
BEFORE `append` returns. There is no buffer to lose: a process killed mid-call
leaves a log that ends exactly where the call did (call log v3 contract:
live ≡ stored, append-only, never edited).

Kinds are plain dotted strings so a reader needs no enum to grep a log:
  session.start · session.end            the envelope (outcome, cost)
  stage.enter · stage.handoff             the process moving on
  tool.call · tool.result · tool.error · tool.refused   masked args, never payloads
  confirm.request · confirm.granted · confirm.declined  the caller's yes or no
  saga.fail · saga.compensated            what was undone, last first
  turn.user · turn.agent                  text + metrics (ttft, e2e) from the framework
  stt.final · state                       the audio path (ms-6)

Open source note: framework-agnostic; `Store` is a Protocol, `MemoryStore`
and `SQLiteStore` ship with it, Postgres is one more file.
"""

import time
from collections.abc import Callable
from typing import Any

from core.state.events import Event
from core.state.store import Store
from core.tools import guard

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
    """Append one fact to a context's log, masked, for callers that may not have one.

    A stage, a confirmation and a saga all run in tests and in the console with
    a context that was never given a log, and none of them should carry an
    `if` about it. This is that `if`, written once.

    It is also the one place their payloads are scrubbed: none of them has a
    `ToolSpec` to mask by name, and a confirmation question or a saga cause is
    free text that can easily repeat the caller's name. Everything the session
    already knows to be PII (`tc.pii_values`) is blanked here.
    """
    if getattr(tc, "log", None) is not None:
        tc.log.append(kind, guard.scrub(payload or {}, getattr(tc, "pii_values", ())))
