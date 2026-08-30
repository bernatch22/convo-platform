"""ToolSpec: the contract every business tool declares before the LLM can call it."""

from dataclasses import dataclass, field
from enum import StrEnum


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

    def needs_confirmation(self) -> bool:
        """Irreversible tools always need an explicit confirmation token."""
        return self.requires_confirmation or self.side_effect is SideEffect.IRREVERSIBLE

    def masks(self, arg: str) -> bool:
        """Whether an argument must be masked before it reaches any log."""
        return arg in self.pii_scope
