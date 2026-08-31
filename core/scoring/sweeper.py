"""The small worker api-side: every few seconds, score the calls that have ended unscored.

This is the answer to "who runs the scorer", and the answer is deliberately not
the job process. A poll beats a callback here for one reason worth stating: a
job killed by the box — SIGKILL, an OOM, a redeploy mid-call — never gets to
tell anybody it is gone, and those are precisely the calls whose score somebody
wants to see. A sweeper over the log needs nothing from the dying process; it
reads what the log already contains and notices the silence.

Three limits keep it boring:

- `BATCH` sessions per tick, so a box that comes back after an outage with
  three hundred unscored calls spends its judge budget over minutes and can be
  switched off halfway.
- `WINDOW_S` back from now, so it never re-walks a year of history looking for
  work that is not there.
- Idempotency lives in the store, not here (`runner.score_session`): two
  control planes on one database is a supported shape, not a race.

`SCORING_SWEEP=0` turns it off entirely — a deploy that wants scoring only from
the CLI, or a test that wants no background work at all.
"""

import asyncio
import logging
import os
import time

from core.scoring import report as scoring_report
from core.scoring.runner import score_session
from core.state.store import SQLiteStore, Store

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
    """Score up to `BATCH` finished, unscored sessions; returns the ids it scored.

    The store is opened HERE, inside the worker thread that will read it: a
    SQLite connection belongs to the thread that created it, and this is the
    one place in the control plane where the reader is not a request handler.
    """
    store = store or SQLiteStore()
    scored: list[str] = []
    for session_id in due(store, now=now)[:BATCH]:
        result = score_session(session_id, store)
        if result["scored"]:
            scored.append(session_id)
    return scored


def due(store: Store, now: float | None = None) -> list[str]:
    """The sessions waiting for a score: recent, finished, and not scored yet — oldest first.

    Oldest first so a backlog drains in the order the calls happened, which is
    the order somebody reading the console down the page expects them in.
    """
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
