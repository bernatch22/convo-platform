"""The chat history, kept provider-safe: never half a tool exchange.

Decisions: docs/decisions/convo.session.history.md
"""

import logging

from livekit.agents.llm import ChatContext

log = logging.getLogger("platform.history")

CALL = "function_call"
OUTPUT = "function_call_output"


def sanitize_tool_pairing(chat_ctx: ChatContext) -> ChatContext:
    """Return the history with every orphaned tool call, and every orphaned result, removed."""
    items = list(chat_ctx.items)
    called = {item.call_id for item in items if item.type == CALL}
    answered = {item.call_id for item in items if item.type == OUTPUT}
    kept = [item for item in items if _paired(item, called, answered)]
    dropped = len(items) - len(kept)
    if dropped:
        log.warning("dropped %d orphaned tool item(s) from the chat context", dropped)
    return ChatContext(kept)


def orphans(chat_ctx: ChatContext) -> list[str]:
    """The `call_id`s that are only half a tool exchange — the reason a 400 would come back."""
    called = {item.call_id for item in chat_ctx.items if item.type == CALL}
    answered = {item.call_id for item in chat_ctx.items if item.type == OUTPUT}
    return sorted(called ^ answered)


def _paired(item, called: set[str], answered: set[str]) -> bool:
    """True when this item is not a tool item, or is one whose other half is present."""
    if item.type == CALL:
        return item.call_id in answered
    if item.type == OUTPUT:
        return item.call_id in called
    return True
