"""guard: the platform's veto on a tool call, and the mask that keeps PII out of the logs.

Framework-agnostic on purpose: `check` and `mask` take a `ToolSpec` and a plain
dict, so any agent runtime can reuse them. `check` is the single place that
decides whether a call may happen at all — the executor never second-guesses it.
"""

from typing import Any

from core.confirm import ConfirmationToken
from core.tools.contract import ToolSpec

MASK_CHAR = "*"
KEPT_CHARS = 2


class ToolRefused(Exception):
    """The platform refuses to run this call; `reason` is written for a developer, not a caller."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check(spec: ToolSpec, args: dict[str, Any], tc: Any) -> None:
    """Veto a tool call before it reaches an adapter: returns None, or raises ToolRefused.

    Two rules: a spec must declare a positive timeout, and an irreversible tool
    must carry a confirmation token minted for exactly this call, still fresh
    and not yet spent. Refusing is not an error the LLM sees; the calling stage
    decides what to say (it asks for confirmation).
    """
    if spec.timeout_s <= 0:
        raise ToolRefused(f"{spec.name} declares timeout_s={spec.timeout_s}; it must be > 0")
    if spec.needs_confirmation():
        raise_unless_confirmed(spec, args, tc)


def raise_unless_confirmed(spec: ToolSpec, args: dict[str, Any], tc: Any) -> None:
    """The confirmation rule on its own, naming which of the four conditions failed."""
    token = getattr(tc, "confirmation_token", None)
    if not isinstance(token, ConfirmationToken):
        raise ToolRefused(f"{spec.name} is {spec.side_effect} and carries no confirmation token")
    if token.used:
        raise ToolRefused(f"{spec.name}: the confirmation token was already spent")
    if token.expired():
        raise ToolRefused(f"{spec.name}: the confirmation token expired after {token.ttl_s}s")
    if not token.valid_for(spec.name, args):
        raise ToolRefused(f"{spec.name}: the confirmation token was minted for another call")


def consume(spec: ToolSpec, tc: Any) -> None:
    """Spend the context's token once an irreversible call has run; a no-op for other tools."""
    token = getattr(tc, "confirmation_token", None)
    if spec.needs_confirmation() and isinstance(token, ConfirmationToken):
        token.consume()


def mask(spec: ToolSpec, payload: dict[str, Any]) -> dict[str, Any]:
    """A copy of the payload with every `pii_scope` argument reduced to `xx****`.

    Two characters survive so a human reading a log can still tell two values
    apart; everything a person could be identified by is gone.
    """
    return {key: _mask_value(value) if spec.masks(key) else value for key, value in payload.items()}


def _mask_value(value: Any) -> str:
    text = str(value)
    if len(text) <= KEPT_CHARS:
        return MASK_CHAR * len(text)
    return text[:KEPT_CHARS] + MASK_CHAR * (len(text) - KEPT_CHARS)
