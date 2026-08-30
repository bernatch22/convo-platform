"""Adapter: the port a tenant implements to reach its own systems (CRM, agenda, ERP)."""

from abc import ABC, abstractmethod
from typing import Any


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
