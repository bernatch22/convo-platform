"""Event: one line of the append-only session log, numbered by `seq`."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    """A fact that happened in a session, in order, never edited."""

    seq: int
    kind: str
    t_ms: int
    payload: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """One-line rendering for terminals and reports."""
        return f"{self.seq:>4} {self.t_ms:>7}ms {self.kind}"
