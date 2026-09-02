"""ToolSpec: the contract every business tool declares before the LLM can call it.

Decisions: docs/decisions/convo.domain.tools.md
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SideEffect(StrEnum):
    """What a tool does to the world; drives confirmation, retries and logging."""

    READ = "read"
    WRITE = "write"
    IRREVERSIBLE = "irreversible"


@dataclass(frozen=True)
class ToolSpec:
    """Declarative contract of a tool: side effect, idempotency, PII, timeout, undo."""

    name: str
    side_effect: SideEffect
    idempotency_key: str | None = None
    pii_scope: frozenset[str] = field(default_factory=frozenset)
    timeout_s: float = 8.0
    compensation: str | None = None
    requires_confirmation: bool = False
    result_summary: Callable[[Any], str] | None = None
    infrastructure: bool = False

    def is_business_tool(self) -> bool:
        """Whether this tool acts on the customer's business — false for platform plumbing."""
        return not self.infrastructure

    def needs_confirmation(self) -> bool:
        """Irreversible tools always need an explicit confirmation token."""
        return self.requires_confirmation or self.side_effect is SideEffect.IRREVERSIBLE

    def masks(self, arg: str) -> bool:
        """Whether an argument must be masked before it reaches any log."""
        return arg in self.pii_scope

    def summarise(self, result: Any) -> str | None:
        """The one line this tool's result may leave in the log, or None when it declares none."""
        if self.result_summary is None:
            return None
        return self.result_summary(result)
