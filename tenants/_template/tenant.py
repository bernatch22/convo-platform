"""Example Co — the tenant template. Copy the folder, rename, and replace every TODO.

Decisions: docs/decisions/tenants._template.tenant.md
"""

from dataclasses import dataclass

from convo.adapters.base import Adapter
from convo.domain.context import Tenant

from .projects.example.project import PROJECT


@dataclass
class ExampleTenant(Tenant):
    """The business and the systems it runs; fakes here, real integrations in yours."""

    def build_adapters(self) -> dict[str, Adapter]:
        """One adapter per system this business owns, built fresh for each session."""
        from .adapters.bookings import FakeBookings

        return {"bookings": FakeBookings()}


TENANT = ExampleTenant(
    id="example-co",
    name="Example Co",
    region="eu",
    projects={PROJECT.id: PROJECT},
)
