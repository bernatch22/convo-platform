"""Tienda Sur — demo tenant: order status and cancellations for an online clothes shop.

The second business on the same worker, and the point of it: nothing in `core/`
knows a clinic from a shop. What changes between the two tenants is data —
adapters, prompts, knowledge, tools, voice and register — and what does not
change is every line of the runtime that carries them.
"""

from dataclasses import dataclass

from convo.adapters.base import Adapter
from convo.domain.context import Tenant

from .projects.pedidos.project import PROJECT


@dataclass
class TiendaSurTenant(Tenant):
    """The shop and the systems it runs; today they are fakes, the seam is real."""

    def build_adapters(self) -> dict[str, Adapter]:
        """One adapter per system the shop owns, built fresh for each session.

        Three of them: the order system, the helpdesk and the SMS gateway. The
        executor picks whichever one declares the capability a tool asks for, so
        adding a system (a payment gateway, a returns portal) is adding a line
        here — no stage and no tool changes. The helpdesk is the proof: it
        arrived a whole milestone later and this is the only line of wiring it
        needed.

        Order matters for exactly one reader. The console asks every system that
        offers a record view for it (`core.business`), and it draws them in this
        order, so the orders the shop lives on lead and the incident queue
        follows.
        """
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
