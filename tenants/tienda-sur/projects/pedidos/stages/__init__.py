"""The stages of an order call, in the order a caller meets them.

Decisions: docs/decisions/tenants.tienda-sur.projects.pedidos.stages.md
"""

from .farewell import Farewell
from .identify import Identify
from .order_desk import OrderDesk
from .ticket_desk import TicketDesk

__all__ = ["Farewell", "Identify", "OrderDesk", "TicketDesk"]
