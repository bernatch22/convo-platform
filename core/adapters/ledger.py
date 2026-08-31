"""Ledger: one JSON file on the box standing in for the customer's own database.

A demo adapter is built fresh per session and keeps its book in memory, which
is right for a conversation and useless for a console: the control plane is a
different process, so an appointment booked in a call would never be visible
to anyone who was not on that call. A real deployment has no such problem —
the agenda is a system both processes reach over HTTP — so the fake needs the
one property the real thing already has: the rows outlive the process that
wrote them, and a second process can read them.

That is all this is. It is not a second event log and it is not a cache of one:
the append-only log records what the PLATFORM did (`core/outcomes.py` counts
transactions off it, and its summaries are PII-filtered by design). This file
records what the BUSINESS SYSTEM now holds — the reservation itself, with the
name on it — because a booking system is exactly the place a customer's own
data is allowed to live, and an operator console is exactly who it is for.

Two decisions worth arguing with.

**Write-through, never read back into a conversation.** An adapter records a
row here after it writes it, and nothing in a session ever reads it: the
in-memory book stays the seeded demo book, so a call behaves identically to
the way it did before this file existed and no test can be contaminated by
what another one wrote. The console reads the ledger, merged over the seed —
which is the business system's current table, and the only reader that needs
it.

**Last write wins, no locking.** Read the file, replace one row, write it back
through `os.replace` so a reader never sees a half-written file. Two calls
finishing in the same millisecond could lose one row; a demo box does a few
transactions an hour, and the fix for real volume is not a lock file, it is
the real system this file is standing in for.

The path is `CONVO_LEDGER`, defaulting beside the SQLite control plane in
`tmp/`. Tests point it at their own tmp directory (`tests/conftest.py`), which
is why the unit ring never touches the box's book.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("platform.ledger")

DEFAULT_PATH = "tmp/business.json"
PATH_ENV = "CONVO_LEDGER"


class Ledger:
    """The rows one fake system has recorded, durable across processes, keyed by the id it gave."""

    def __init__(self, book: str, path: str | os.PathLike[str] | None = None) -> None:
        self.book = book
        self.path = Path(path or os.getenv(PATH_ENV, DEFAULT_PATH))

    def rows(self) -> dict[str, dict[str, Any]]:
        """Every row this book holds today, newest standing, keyed by the business's own id."""
        return dict(self._read().get(self.book, {}))

    def record(self, key: str, row: dict[str, Any]) -> None:
        """Write one row through: a record that did not exist, or a new standing for one that did.

        The key is the business system's own identifier; an empty one is a bug
        upstream and is dropped rather than filed under the empty string.
        """
        if not key:
            return
        books = self._read()
        books.setdefault(self.book, {})[key] = row
        self._write(books)

    def _read(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Every book in the file, or an empty one — an unreadable ledger is never fatal."""
        try:
            loaded = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}
        except Exception:  # noqa: BLE001 — a corrupt demo file must not break a call
            log.exception("ledger %s is unreadable; treating it as empty", self.path)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _write(self, books: dict[str, Any]) -> None:
        """Replace the file atomically, so a reader in another process never sees half of it."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            scratch = self.path.with_suffix(f"{self.path.suffix}.{os.getpid()}")
            scratch.write_text(json.dumps(books, ensure_ascii=False, indent=2))
            os.replace(scratch, self.path)
        except Exception:  # noqa: BLE001 — the call already succeeded; the console can miss a row
            log.exception("ledger %s could not be written", self.path)
