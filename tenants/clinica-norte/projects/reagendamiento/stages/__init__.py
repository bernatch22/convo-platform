"""The three stages of a rescheduling call, in the order a caller meets them.

Identify finds out whose appointment this is, ChooseSlot reads the agenda and
books the hour the patient picks, Farewell closes the call. Each one is a
`TenantAgent` with its own prompt and its own tools, and a stage moves the call
on by returning the next stage from a tool — so the transition is a thing that
happened, recorded in the run, and not a flag somebody set.
"""

from .choose_slot import ChooseSlot
from .farewell import Farewell
from .identify import Identify

__all__ = ["ChooseSlot", "Farewell", "Identify"]
