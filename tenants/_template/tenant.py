"""Example Co — the tenant template. Copy the folder, rename, and replace every TODO.

A tenant is a customer of the platform: its own systems (adapters), its own use
cases (projects) and nothing else. `core/` never imports this package — the
registry finds it on disk by folder name — so everything here is data the
runtime carries, not code the runtime depends on.

TODO(copy): rename the folder to your tenant id, and change `id` and `name`
below. The id is the folder name and the string a dispatch, a route or
`TENANT=` uses to reach this tenant; nothing else may name it.
"""

from dataclasses import dataclass

from convo.adapters.base import Adapter
from convo.domain.context import Tenant

from .projects.example.project import PROJECT


@dataclass
class ExampleTenant(Tenant):
    """The business and the systems it runs; fakes here, real integrations in yours."""

    def build_adapters(self) -> dict[str, Adapter]:
        """One adapter per system this business owns, built fresh for each session.

        The executor picks whichever adapter declares the capability a tool
        asks for, so adding a system (a payment gateway, a CRM) is adding a
        line here — no stage and no tool changes.

        TODO(copy): one entry per system of yours. The keys are yours to choose;
        what matters is the capability names the adapters declare.
        """
        from .adapters.bookings import FakeBookings

        return {"bookings": FakeBookings()}


TENANT = ExampleTenant(
    id="example-co",
    name="Example Co",
    region="eu",
    projects={PROJECT.id: PROJECT},
)
