"""The stages of a call to Clínica Norte's reception, in the order a caller meets them.

Identify finds out whose call this is. From there the call goes one of three
ways: a patient the book already holds moves their hour in ChooseSlot, a patient
it does not gets a first one in NewBooking, and a patient whose number the clinic
has wrong fixes it in UpdateContact. Farewell closes a booking. Each stage is a
`TenantAgent` with its own prompt and its own tools, and a stage moves the call
on by returning the next stage from a tool — so the transition is a thing that
happened, recorded in the run, and not a flag somebody set.

The two booking stages read the agenda the same way on purpose: the prompt
paragraphs are shared (`prompts/reception.py`) and the hour helpers are shared
(`tools.py`). What each owns alone is what its errand owns alone — a cita to
release, or a patient with nothing to fall back on.

UpdateContact shares less than either, and deliberately: it never reads the
agenda, and the only thing it inherits from reception is how the clinic speaks.
What it owns alone is the rule that gives the errand its shape — the value it is
about to change is a value it may not read out.
"""

from .choose_slot import ChooseSlot
from .farewell import Farewell
from .identify import Identify
from .new_booking import NewBooking
from .update_contact import UpdateContact

__all__ = ["ChooseSlot", "Farewell", "Identify", "NewBooking", "UpdateContact"]
