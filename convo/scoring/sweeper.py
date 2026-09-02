"""The small worker api-side: every few seconds, score the calls that have ended unscored.

Decisions: docs/decisions/convo.scoring.sweeper.md
"""

import asyncio
import logging
import os
import time

from convo.scoring import report as scoring_report
from convo.scoring.runner import score_session
from convo.state.store import SQLiteStore, Store

log = logging.getLogger("platform.scoring")

INTERVAL_S = float(os.getenv("SCORING_SWEEP_S", "10"))
WINDOW_S = float(os.getenv("SCORING_WINDOW_S", "86400"))
BATCH = int(os.getenv("SCORING_BATCH", "3"))
ENABLED_ENV = "SCORING_SWEEP"


def enabled() -> bool:
    """Whether this control plane scores the calls it stores; `SCORING_SWEEP=0` says no."""
    return os.getenv(ENABLED_ENV, "1") not in ("0", "false", "no")


async def run(interval_s: float = INTERVAL_S) -> None:
    """Sweep forever, one tick every `interval_s`; cancelled when the app shuts down."""
    log.info("post-call scoring: sweeping every %ss, %s sessions a tick", interval_s, BATCH)
    while True:
        try:
            await asyncio.to_thread(tick)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a bad tick must not end the sweep
            log.exception("scoring sweep failed; retrying at the next tick")
        await asyncio.sleep(interval_s)


def tick(store: Store | None = None, now: float | None = None) -> list[str]:
    """Score up to `BATCH` finished, unscored sessions; returns the ids it scored."""
    store = store or SQLiteStore()
    scored: list[str] = []
    for session_id in due(store, now=now)[:BATCH]:
        result = score_session(session_id, store)
        if result["scored"]:
            scored.append(session_id)
    return scored


def due(store: Store, now: float | None = None) -> list[str]:
    """The sessions waiting for a score: recent, finished, and not scored yet — oldest first."""
    now = now or time.time()
    waiting = []
    for row in store.sessions():
        if now - row.started_at > WINDOW_S:
            break  # `sessions()` is newest first: everything below is older still
        events = store.events(row.id)
        if scoring_report.already_scored(events) is not None:
            continue
        if scoring_report.finished(row, events, now=now):
            waiting.append(row.id)
    return list(reversed(waiting))
