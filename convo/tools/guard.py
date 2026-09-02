"""guard: the platform's veto on a tool call, and the mask that keeps PII out of the logs.

Decisions: docs/decisions/convo.tools.guard.md
"""

from collections.abc import Iterable
from typing import Any

from convo.domain.tools import ToolSpec
from convo.tools.confirm import ConfirmationToken

MASK_CHAR = "*"
KEPT_CHARS = 2
# A value shorter than this is never used as a pattern: masking every "53" in a
# log would destroy the line without protecting anybody.
MIN_PATTERN_CHARS = KEPT_CHARS + 1


class ToolRefused(Exception):
    """The platform refuses to run this call; `reason` is written for a developer, not a caller."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check(spec: ToolSpec, args: dict[str, Any], tc: Any) -> None:
    """Veto a tool call before it reaches an adapter: returns None, or raises ToolRefused."""
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


def mask(spec: ToolSpec, payload: dict[str, Any], known: Iterable[str] = ()) -> dict[str, Any]:
    """A copy of the payload with every `pii_scope` argument reduced to `xx****`."""
    patterns = _patterns(known)
    return {
        key: _mask_value(value) if spec.masks(key) else _scrub(value, patterns)
        for key, value in payload.items()
    }


def scrub(payload: Any, known: Iterable[str]) -> Any:
    """The same payload with every known PII value masked wherever a string carries it."""
    return _scrub(payload, _patterns(known))


def learn(known: set[str], values: Iterable[Any]) -> set[str]:
    """Add every value long enough to mask by to `known`, in place; returns it."""
    known.update(text for text in map(_text, values) if len(text) >= MIN_PATTERN_CHARS)
    return known


def pii_values(spec: ToolSpec, args: dict[str, Any]) -> list[Any]:
    """The values of this call's `pii_scope` arguments — what the executor learns from."""
    return [args.get(key) for key in spec.pii_scope]


def _patterns(known: Iterable[str]) -> tuple[str, ...]:
    """Maskable values, longest first, so a full name is masked before its first word."""
    usable = {text for text in map(_text, known) if len(text) >= MIN_PATTERN_CHARS}
    return tuple(sorted(usable, key=len, reverse=True))


def _scrub(value: Any, patterns: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return _mask_occurrences(value, patterns)
    if isinstance(value, dict):
        return {key: _scrub(item, patterns) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(item, patterns) for item in value]
    return value


def _mask_occurrences(text: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        if pattern in text:
            text = text.replace(pattern, _mask_value(pattern))
    return text


def _mask_value(value: Any) -> str:
    text = str(value)
    if len(text) <= KEPT_CHARS:
        return MASK_CHAR * len(text)
    return text[:KEPT_CHARS] + MASK_CHAR * (len(text) - KEPT_CHARS)


def _text(value: Any) -> str:
    """A value as a masking pattern: `None` is nothing, never the four letters."""
    return "" if value is None else str(value).strip()
