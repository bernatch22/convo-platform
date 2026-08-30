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
    """One stage's system prompt: the project's knowledge first, then who this stage is."""
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
        ]
    )
