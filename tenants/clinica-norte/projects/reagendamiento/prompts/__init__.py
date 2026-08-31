"""Prompts of the reagendamiento project, one per stage. Project data: edit here, never in core.

Shape follows Anthropic's current prompting guidance for Claude 4.x / Haiku 4.5:
one-sentence role, long stable knowledge first, instructions that explain why,
success described instead of prohibitions, a few examples in <example> tags,
prose over bullets (the prompt's format leaks into spoken output).

The paragraphs the two booking stages share — always consult the agenda, offer
what came back, let the tool ask for the yes — live in `reception.py` and are
composed, never copied. The split that created it was byte-identical, so a new
errand joined the project without moving the ring underneath the old one; what
each stage is made of is pinned by `tests/test_prompts.py`.

Every stage assembles its prompt through `stage_prompt`, which puts the same
`<clinic_knowledge>` block first, byte for byte. Two reasons, and the second is
the expensive one:

- what the clinic is does not change between stages. A patient who asks the
  price of a resonancia while choosing an hour gets the same answer as in the
  first ten seconds of the call.
- Haiku 4.5 only caches a prompt prefix of 4096 tokens or more. That block is
  4360 on its own, so every stage clears the floor before it has written a
  single instruction of its own — and the cache is read from the second turn of
  each stage. Nothing dated, numbered or per-request may ever enter it: one
  timestamp in there and every stage pays full price on every turn.
"""

from core.context import TenantContext
from core.security.protocol import SUPERVISOR_PROTOCOL
from core.telephony import human

from .cancel_or_confirm import (
    CANCEL_OR_CONFIRM_EXAMPLES,
    CANCEL_OR_CONFIRM_INSTRUCTIONS,
    CANCEL_OR_CONFIRM_ROLE,
    CONFIRM_CANCELLATION_INSTRUCTIONS,
)
from .choose_slot import (
    CHOOSE_SLOT_EXAMPLES,
    CHOOSE_SLOT_INSTRUCTIONS,
    CHOOSE_SLOT_ROLE,
    CONFIRM_INSTRUCTIONS,
)
from .farewell import FAREWELL_EXAMPLES, FAREWELL_INSTRUCTIONS, FAREWELL_ROLE
from .identify import IDENTIFY_EXAMPLES, IDENTIFY_INSTRUCTIONS, IDENTIFY_ROLE
from .new_booking import (
    CONFIRM_NEW_BOOKING_INSTRUCTIONS,
    NEW_BOOKING_EXAMPLES,
    NEW_BOOKING_INSTRUCTIONS,
    NEW_BOOKING_ROLE,
)
from .update_contact import (
    CONFIRM_CONTACT_INSTRUCTIONS,
    UPDATE_CONTACT_EXAMPLES,
    UPDATE_CONTACT_INSTRUCTIONS,
    UPDATE_CONTACT_ROLE,
)

__all__ = [
    "cancel_or_confirm_prompt",
    "choose_slot_prompt",
    "confirm_cancellation_instructions",
    "confirm_contact_instructions",
    "confirm_instructions",
    "confirm_new_booking_instructions",
    "farewell_prompt",
    "identify_prompt",
    "new_booking_prompt",
    "stage_prompt",
    "update_contact_prompt",
]


def identify_prompt(tc: TenantContext) -> str:
    """The stage that opens the call and finds out whose appointment this is."""
    return stage_prompt(tc, IDENTIFY_ROLE, IDENTIFY_INSTRUCTIONS, IDENTIFY_EXAMPLES)


def choose_slot_prompt(tc: TenantContext) -> str:
    """The stage that reads the agenda, offers real hours and books the one chosen."""
    return stage_prompt(tc, CHOOSE_SLOT_ROLE, CHOOSE_SLOT_INSTRUCTIONS, CHOOSE_SLOT_EXAMPLES)


def cancel_or_confirm_prompt(tc: TenantContext) -> str:
    """The stage for the cita a caller already has: read it back, then cancel or confirm it."""
    return stage_prompt(
        tc, CANCEL_OR_CONFIRM_ROLE, CANCEL_OR_CONFIRM_INSTRUCTIONS, CANCEL_OR_CONFIRM_EXAMPLES
    )


def new_booking_prompt(tc: TenantContext) -> str:
    """The stage that gives a first cita to a caller the appointment book did not hold."""
    return stage_prompt(tc, NEW_BOOKING_ROLE, NEW_BOOKING_INSTRUCTIONS, NEW_BOOKING_EXAMPLES)


def update_contact_prompt(tc: TenantContext) -> str:
    """The stage that validates the number on file by its last digits and changes it."""
    return stage_prompt(
        tc, UPDATE_CONTACT_ROLE, UPDATE_CONTACT_INSTRUCTIONS, UPDATE_CONTACT_EXAMPLES
    )


def confirm_instructions() -> str:
    """The prompt ConfirmTask asks with when a cita is being MOVED, in the clinic's register."""
    return CONFIRM_INSTRUCTIONS


def confirm_new_booking_instructions() -> str:
    """The same, for a cita being CREATED: there is no earlier hour to promise back."""
    return CONFIRM_NEW_BOOKING_INSTRUCTIONS


def confirm_cancellation_instructions() -> str:
    """The same, for a cita being CANCELLED: what is read back is the cita it is about to lose."""
    return CONFIRM_CANCELLATION_INSTRUCTIONS


def confirm_contact_instructions() -> str:
    """The same, for a contact number being REPLACED: what is read back is digits, not an hour."""
    return CONFIRM_CONTACT_INSTRUCTIONS


def farewell_prompt(tc: TenantContext) -> str:
    """The stage that closes the call once the change is done."""
    return stage_prompt(tc, FAREWELL_ROLE, FAREWELL_INSTRUCTIONS, FAREWELL_EXAMPLES)


def stage_prompt(tc: TenantContext, role: str, instructions: str, examples: str = "") -> str:
    """One stage's system prompt: the project's knowledge first, then who this stage is.

    The supervisor protocol closes it: a human listening to the call can whisper
    an instruction mid-conversation, and a persona that has not been told those
    exist ranks its own script above them and ignores the whisper (measured 0/3;
    3/3 with this paragraph — `core.security.protocol`). It is fixed text, so it
    rides inside the cached prefix and costs nothing per turn.

    The transfer paragraph closes it only when there IS one: `human.protocol`
    answers "" for a project that names no `transfer_number`, so the rule and
    the tool appear and disappear together. A rule about a tool the model does
    not have is the surest way to have it reach for one.
    """
    return "\n".join(
        [
            "<clinic_knowledge>",
            tc.project.knowledge(tc),
            "</clinic_knowledge>",
            "",
            role,
            "",
            instructions,
            examples,
            SUPERVISOR_PROTOCOL,
            human.protocol(tc.project),
        ]
    )
