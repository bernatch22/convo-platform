"""Tienda Sur — demo tenant: order status and cancellations for an online clothes shop.

Decisions: docs/decisions/tenants.tienda-sur.tenant.md
"""

from dataclasses import dataclass

from convo.adapters.base import Adapter
from convo.domain.context import Tenant

from .projects.pedidos.project import PROJECT


@dataclass
class TiendaSurTenant(Tenant):
    """The shop and the systems it runs; today they are fakes, the seam is real."""

    def build_adapters(self) -> dict[str, Adapter]:
        """One adapter per system the shop owns, built fresh for each session."""
        from .adapters.orders import FakeOrders
        from .adapters.sms import FakeSms
        from .adapters.tickets import FakeTickets

        return {"orders": FakeOrders(), "tickets": FakeTickets(), "sms": FakeSms()}


TENANT = TiendaSurTenant(
    id="tienda-sur",
    name="Tienda Sur",
    region="eu",
    projects={PROJECT.id: PROJECT},
)
