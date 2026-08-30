"""The three stages of an order call, in the order a caller meets them.

Identify finds out which order this is about, OrderDesk says where it is and
cancels it while the warehouse still can, Farewell closes the call. Each one is
a `TenantAgent` with its own prompt and its own tools, and a stage moves the
call on by returning the next stage from a tool — so the transition is a thing
that happened, recorded in the run, and not a flag somebody set.
"""

from .farewell import Farewell
from .identify import Identify
from .order_desk import OrderDesk

__all__ = ["Farewell", "Identify", "OrderDesk"]
