"""The shape of a score, and the three questions about a log that decide when one is written.

Decisions: docs/decisions/convo.scoring.report.md
"""

import time
from dataclasses import dataclass, field
from typing import Any

from convo.state.events import Event
from convo.state.store import SessionRow

SCORE_KIND = "session.score"
END_KIND = "session.end"
VERSION = 1

# How long a log must have been silent before a call with no close event is read
# as over. Two minutes is longer than any gap inside a real conversation and
# short enough that a SIGKILLed call is still scored within the minute the
# console promises after the caller hangs up.
STALE_S = 120.0

DETERMINISTIC = "deterministic"
JUDGE = "judge"


@dataclass(frozen=True)
class Check:
    """One question asked of a finished call, and the answer with its evidence."""

    name: str
    passed: bool | None
    reason: str
    kind: str = DETERMINISTIC
    score: float | None = None

    def value(self) -> float | None:
        """What this check contributes to the average: the judge's number, or 1.0/0.0."""
        if self.passed is None:
            return None
        return self.score if self.score is not None else float(self.passed)

    def as_dict(self) -> dict[str, Any]:
        """The check as one entry of the `session.score` payload."""
        row: dict[str, Any] = {"name": self.name, "kind": self.kind, "passed": self.passed}
        if self.score is not None:
            row["score"] = round(self.score, 3)
        row["reason"] = self.reason
        return row


@dataclass(frozen=True)
class JudgeRun:
    """What the one LLM call did, or why it was never made — the cap's audit trail."""

    ran: bool
    model: str
    threshold: float
    cap_eur: float
    cost_eur: float = 0.0
    skipped: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ran": self.ran,
            "skipped": self.skipped,
            "model": self.model,
            "threshold": self.threshold,
            "cap_eur": round(self.cap_eur, 6),
            "cost_eur": round(self.cost_eur, 6),
        }


@dataclass(frozen=True)
class ScoreReport:
    """Every check this call earned, the number they average to, and the verdict."""

    checks: list[Check] = field(default_factory=list)
    judge: JudgeRun | None = None
    turns: int = 0

    def score(self) -> float:
        """The mean of every check that applied, 0-1; 1.0 when nothing could be checked."""
        values = [value for value in (check.value() for check in self.checks) if value is not None]
        return round(sum(values) / len(values), 3) if values else 1.0

    def verdict(self) -> str:
        """`pass` only when every applicable check passed — one red line makes the call red."""
        return "pass" if all(check.passed is not False for check in self.checks) else "fail"

    def failed(self) -> list[str]:
        """The names of the checks that said no, in order — what a chip's tooltip shows."""
        return [check.name for check in self.checks if check.passed is False]

    def payload(self) -> dict[str, Any]:
        """The `session.score` event's payload, exactly as the log stores it."""
        return {
            "version": VERSION,
            "score": self.score(),
            "verdict": self.verdict(),
            "failed": self.failed(),
            "turns": self.turns,
            "checks": [check.as_dict() for check in self.checks],
            "judge": self.judge.as_dict() if self.judge else None,
        }


def finished(row: SessionRow, events: list[Event], now: float | None = None) -> bool:
    """Is this call over? Closed, ended in its own log, or silent long enough to be gone."""
    if row.outcome is not None or row.ended_at is not None:
        return True
    if not events:
        return False
    if events[-1].kind == END_KIND:
        return True
    last_seen = row.started_at + events[-1].t_ms / 1000
    return (now or time.time()) - last_seen >= STALE_S


def already_scored(events: list[Event]) -> dict[str, Any] | None:
    """The payload of this session's score, or None — the idempotency read, and the UI's."""
    for event in reversed(events):
        if event.kind == SCORE_KIND:
            return event.payload
    return None


def next_seq(events: list[Event]) -> int:
    """The seq a score written now would take: one past the highest the log holds."""
    return max((event.seq for event in events), default=0) + 1
