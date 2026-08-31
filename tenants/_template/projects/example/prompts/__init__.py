"""Prompts of the example project, one per stage. Project data: edit here, never in core.

Shape follows Anthropic's current guidance for Claude 4.x / Haiku 4.5:
one-sentence role, the long stable knowledge FIRST, instructions that explain
why, success described instead of prohibitions, a few examples in <example>
tags, prose over bullets (the prompt's format leaks into spoken output).

Every stage assembles its prompt through `stage_prompt`, which puts the same
`<business_knowledge>` block first, byte for byte. That is not tidiness: Haiku
4.5 only caches a prefix of 4096+ tokens and only while it is identical, so the
shared block is what gets every stage over the floor before it writes an
instruction of its own.

TODO(copy): rename the tag to your business, and write one module per stage.
The register — usted or tú, and which — lives in these files and in the
project's `messages`, and in nothing under `core/`.
"""

from core.context import TenantContext
from core.security.protocol import SUPERVISOR_PROTOCOL
from core.telephony import human

from .desk import CONFIRM_INSTRUCTIONS, DESK_EXAMPLES, DESK_INSTRUCTIONS, DESK_ROLE
from .reception import RECEPTION_EXAMPLES, RECEPTION_INSTRUCTIONS, RECEPTION_ROLE

__all__ = ["confirm_instructions", "desk_prompt", "reception_prompt", "stage_prompt"]


def reception_prompt(tc: TenantContext) -> str:
    """The stage that opens the call and finds out which booking it is about."""
    return stage_prompt(tc, RECEPTION_ROLE, RECEPTION_INSTRUCTIONS, RECEPTION_EXAMPLES)


def desk_prompt(tc: TenantContext) -> str:
    """The stage that reads the booking back and cancels it once the customer says yes."""
    return stage_prompt(tc, DESK_ROLE, DESK_INSTRUCTIONS, DESK_EXAMPLES)


def confirm_instructions() -> str:
    """The prompt ConfirmTask asks with, in this business's own register."""
    return CONFIRM_INSTRUCTIONS


def stage_prompt(tc: TenantContext, role: str, instructions: str, examples: str = "") -> str:
    """One stage's system prompt: the project's knowledge first, then who this stage is.

    The supervisor protocol closes it: a human listening to the call can whisper
    an instruction mid-conversation, and a persona that has not been told those
    exist ranks its own script above them and ignores the whisper (measured 0/3;
    3/3 with this paragraph — `core.security.protocol`). It is fixed text, so it
    rides inside the cached prefix and costs nothing per turn.

    The transfer paragraph sits just BEFORE it, and `human.protocol` answers ""
    for a project that never declared the verb, so that rule and its tool appear
    together — a rule about a tool the model does not have is the surest way to
    have it reach for one.

    The last slot is the supervisor rule's to keep: the final paragraph is the
    most recent instruction the model reads, and `SUPERVISOR_PROTOCOL` is the one
    that exists to outrank the stage script (0/3 without it, 3/3 with —
    `core.security.protocol`). That is the whole argument for the order. It was
    ALSO the prime suspect in an ms-20 flake and it was innocent: moving it
    changed nothing measurable (p=1.0). `core.telephony.human.protocol` carries
    the 154 runs that say so, and what they blame instead.
    """
    return "\n".join(
        [
            "<business_knowledge>",
            tc.project.knowledge(tc),
            "</business_knowledge>",
            "",
            role,
            "",
            instructions,
            examples,
            human.protocol(tc.project),
            SUPERVISOR_PROTOCOL,
        ]
    )
