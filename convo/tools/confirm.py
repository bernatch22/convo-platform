"""ConfirmationToken: the proof that a caller said yes to one concrete irreversible action.

Decisions: docs/decisions/convo.tools.confirm.md
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

DEFAULT_TTL_S = 120.0
AUDIENCE_DIGEST_CHARS = 16


@dataclass
class ConfirmationToken:
    """One-shot authorisation of a single tool call: audience, expiry and a used flag."""

    value: str
    audience: str
    minted_at: float
    ttl_s: float = DEFAULT_TTL_S
    used: bool = field(default=False)

    def valid_for(self, tool: str, args: dict[str, Any], now: float | None = None) -> bool:
        """True while the token is unused, unexpired and minted for exactly this call."""
        return self.audience == audience(tool, args) and not self.used and not self.expired(now)

    def expired(self, now: float | None = None) -> bool:
        """Whether the caller's yes is too old to act on."""
        return (now if now is not None else time.time()) - self.minted_at > self.ttl_s

    def consume(self) -> None:
        """Spend the token: the irreversible call ran, a second one needs a fresh yes."""
        self.used = True


def mint(
    tc: Any, tool: str, args: dict[str, Any], ttl_s: float = DEFAULT_TTL_S
) -> ConfirmationToken:
    """Mint a token for `tool(args)` and hang it on the context, replacing any older one."""
    token = ConfirmationToken(
        value=_value(tool, args),
        audience=audience(tool, args),
        minted_at=time.time(),
        ttl_s=ttl_s,
    )
    tc.confirmation_token = token
    return token


def audience(tool: str, args: dict[str, Any]) -> str:
    """`tool:digest` — the call a token stands for; a different argument is a different call."""
    canonical = json.dumps(args, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:AUDIENCE_DIGEST_CHARS]
    return f"{tool}:{digest}"


def _value(tool: str, args: dict[str, Any]) -> str:
    return hashlib.sha256(f"{audience(tool, args)}:{time.time_ns()}".encode()).hexdigest()[:24]
