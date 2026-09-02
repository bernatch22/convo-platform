"""The stages of a call, in the order a caller meets them.

Decisions: docs/decisions/tenants._template.projects.example.stages.md
"""

from .desk import Desk
from .reception import Reception

__all__ = ["Desk", "Reception"]
