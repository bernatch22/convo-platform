"""Prompts of the reagendamiento project, one per stage. Project data: edit here, never in core.

Shape follows Anthropic's current prompting guidance for Claude 4.x / Haiku 4.5:
one-sentence role, long stable knowledge first, instructions that explain why,
success described instead of prohibitions, a few examples in <example> tags,
prose over bullets (the prompt's format leaks into spoken output).

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

from .choose_slot import (
    CHOOSE_SLOT_EXAMPLES,
    CHOOSE_SLOT_INSTRUCTIONS,
    CHOOSE_SLOT_ROLE,
    CONFIRM_INSTRUCTIONS,
)
from .farewell import FAREWELL_EXAMPLES, FAREWELL_INSTRUCTIONS, FAREWELL_ROLE
from .identify import IDENTIFY_EXAMPLES, IDENTIFY_INSTRUCTIONS, IDENTIFY_ROLE

__all__ = [
    "choose_slot_prompt",
    "confirm_instructions",
    "farewell_prompt",
    "identify_prompt",
    "stage_prompt",
]


def identify_prompt(tc: TenantContext) -> str:
    """The stage that opens the call and finds out whose appointment this is."""
    return stage_prompt(tc, IDENTIFY_ROLE, IDENTIFY_INSTRUCTIONS, IDENTIFY_EXAMPLES)


def choose_slot_prompt(tc: TenantContext) -> str:
    """The stage that reads the agenda, offers real hours and books the one chosen."""
    return stage_prompt(tc, CHOOSE_SLOT_ROLE, CHOOSE_SLOT_INSTRUCTIONS, CHOOSE_SLOT_EXAMPLES)


def confirm_instructions() -> str:
    """The prompt ConfirmTask asks with, in the clinic's own register."""
    return CONFIRM_INSTRUCTIONS


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
        ]
    )
