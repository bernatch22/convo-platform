"""The stages of a call to Clínica Norte's reception, in the order a caller meets them.

Identify finds out whose call this is. From there the call goes one of four
ways: a patient the book already holds moves their hour in ChooseSlot, a patient
it does not gets a first one in NewBooking, a patient whose number the clinic has
wrong fixes it in UpdateContact, and a patient who is not moving their cita at all
— dropping it, or saying they will be there — settles it in CancelOrConfirm.
Farewell closes a booking. Each stage is a
`TenantAgent` with its own prompt and its own tools, and a stage moves the call
on by returning the next stage from a tool — so the transition is a thing that
happened, recorded in the run, and not a flag somebody set.

The two booking stages read the agenda the same way on purpose: the prompt
paragraphs are shared (`prompts/reception.py`) and the hour helpers are shared
(`helpers.py`). What each owns alone is what its errand owns alone — a cita to
release, or a patient with nothing to fall back on.

CancelOrConfirm shares three paragraphs and no tool with them. It reads no
agenda — there is no hour to choose, only the one the caller already has — so
what it takes from `reception.py` is how the clinic speaks, how it says an hour
out loud, and what it does with everything that is not the errand. What it owns
alone is the rule the two verbs are built on: the cita is looked up before it is
read back, every time, and the lookup can only ever find the caller's own.

UpdateContact shares less than either, and deliberately: it never reads the
agenda, and the only thing it inherits from reception is how the clinic speaks.
What it owns alone is the rule that gives the errand its shape — the value it is
about to change is a value it may not read out.
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
