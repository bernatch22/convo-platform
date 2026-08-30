"""Prompts of the pedidos project, one per stage. Project data: edit here, never in core.

Shape follows Anthropic's current prompting guidance for Claude 4.x / Haiku 4.5:
one-sentence role, long stable knowledge first, instructions that explain why,
success described instead of prohibitions, a few examples in <example> tags,
prose over bullets (the prompt's format leaks into spoken output).

Every stage assembles its prompt through `stage_prompt`, which puts the same
`<shop_knowledge>` block first, byte for byte. Two reasons, and the second is
the expensive one:

- what the shop is does not change between stages. A customer who asks about
  return windows while cancelling gets the same answer as in the first ten
  seconds of the call.
- Haiku 4.5 only caches a prompt prefix of 4096 tokens or more. That block is
  4550 on its own, so every stage clears the floor before it has written a
  single instruction of its own — and the cache is read from the second turn of
  each stage. Nothing dated, numbered or per-request may ever enter it: one
  order number in there and every stage pays full price on every turn.

The register is the other half of why this folder exists. Clínica Norte speaks
to patients as "usted" and Tienda Sur tutea, and neither fact is written
anywhere in `core/`: it lives in these four files and in the project's own
`messages`.
"""

from core.context import TenantContext

from .farewell import FAREWELL_EXAMPLES, FAREWELL_INSTRUCTIONS, FAREWELL_ROLE
from .identify import IDENTIFY_EXAMPLES, IDENTIFY_INSTRUCTIONS, IDENTIFY_ROLE
from .order_desk import (
    CONFIRM_INSTRUCTIONS,
    ORDER_DESK_EXAMPLES,
    ORDER_DESK_INSTRUCTIONS,
    ORDER_DESK_ROLE,
)

__all__ = [
    "confirm_instructions",
    "farewell_prompt",
    "identify_prompt",
    "order_desk_prompt",
    "stage_prompt",
]


def identify_prompt(tc: TenantContext) -> str:
    """The stage that opens the call and finds out which order it is about."""
    return stage_prompt(tc, IDENTIFY_ROLE, IDENTIFY_INSTRUCTIONS, IDENTIFY_EXAMPLES)


def order_desk_prompt(tc: TenantContext) -> str:
    """The stage that reads the order back and cancels it while the warehouse still can."""
    return stage_prompt(tc, ORDER_DESK_ROLE, ORDER_DESK_INSTRUCTIONS, ORDER_DESK_EXAMPLES)


def confirm_instructions() -> str:
    """The prompt ConfirmTask asks with, in the shop's own register."""
    return CONFIRM_INSTRUCTIONS


def farewell_prompt(tc: TenantContext) -> str:
    """The stage that closes the call once the cancellation is done."""
    return stage_prompt(tc, FAREWELL_ROLE, FAREWELL_INSTRUCTIONS, FAREWELL_EXAMPLES)


def stage_prompt(tc: TenantContext, role: str, instructions: str, examples: str = "") -> str:
    """One stage's system prompt: the project's knowledge first, then who this stage is."""
    return "\n".join(
        [
            "<shop_knowledge>",
            tc.project.knowledge(tc),
            "</shop_knowledge>",
            "",
            role,
            "",
            instructions,
            examples,
        ]
    )
