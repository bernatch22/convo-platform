"""The stages of a call, in the order a caller meets them.

Reception finds out which booking this is about; Desk answers about it and
cancels it. Each one is a `TenantAgent` with its own prompt and its own tools,
and a stage moves the call on by RETURNING the next stage from a tool — so the
transition is a thing that happened, recorded in the run, and not a flag
somebody set.

TODO(copy): one module per phase of your call. Two is a good place to start;
split further the moment a stage's prompt starts saying "si ya has hecho X".
"""

from .desk import Desk
from .reception import Reception

__all__ = ["Desk", "Reception"]
