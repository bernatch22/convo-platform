"""Ledger: one JSON file on the box standing in for the customer's own database.

Decisions: docs/decisions/convo.adapters.ledger.md
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
        """Write one row through: a new record, or a new standing for one that existed."""
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
