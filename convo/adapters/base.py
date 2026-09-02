"""Adapter: the port a tenant implements to reach its own systems (CRM, agenda, ERP).

Decisions: docs/decisions/convo.adapters.base.md
"""

from abc import ABC, abstractmethod
from typing import Any

# The console's read. An adapter that declares it answers `execute(LIST_RECORDS, {})` with
#
#   {"shape": str,                      # what these records are, in the business's own word
#    "labels": {key: str|None},         # the column headings; a missing key is not rendered
#    "rows": [{"id": str,               # the business system's own identifier
#              "who": str,              # the person the record is about
#              "contact": str|None,     # how the business reaches them
#              "when": str|None,        # ISO moment or date the record is FOR
#              "handled_by": str|None,  # the professional, agent or courier on it
#              "state": str,            # how it stands, in the business's own word
#              "tone": str,             # new | changed | gone | plain — how to draw it
#              "detail": str|None,      # one more line the operator wants
#              "at": float|None}]}      # when the business last touched it, epoch seconds
#
# `tone` is the only presentational field and it is deliberately the adapter's
# call: it is the business that knows whether "cancelado" means the record is
# gone, and neither core nor the console holds a list of state words.
LIST_RECORDS = "list_records"

NEW = "new"
CHANGED = "changed"
GONE = "gone"
PLAIN = "plain"


class Adapter(ABC):
    """One adapter per external system; tools call capabilities, never HTTP directly."""

    @abstractmethod
    def capabilities(self) -> list[str]:
        """Capability names this adapter can execute, e.g. ['find_customer', 'book_slot']."""

    @abstractmethod
    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        """Run one capability with validated arguments and return a JSON-serialisable result."""

    def supports(self, capability: str) -> bool:
        """Whether this adapter implements the capability."""
        return capability in self.capabilities()
