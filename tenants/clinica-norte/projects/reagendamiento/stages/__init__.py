"""The stages of a call to Clínica Norte's reception, in the order a caller meets them.

Decisions: docs/decisions/tenants.clinica-norte.projects.reagendamiento.stages.md
"""

from .cancel_or_confirm import CancelOrConfirm
from .choose_slot import ChooseSlot
from .farewell import Farewell
from .identify import Identify
from .new_booking import NewBooking
from .update_contact import UpdateContact

__all__ = [
    "CancelOrConfirm",
    "ChooseSlot",
    "Farewell",
    "Identify",
    "NewBooking",
    "UpdateContact",
]
