"""What a session cost: a price table per provider/model, and the sum over `session.usage`.

The table is EUR per million tokens, derived from the vendors' published USD
list prices at `USD_EUR`. It lives in code, not in a config file, because a
price is an audited fact about a stored session: the log records the euros the
call cost at the rate we believed on the day, and a later repricing must not
rewrite history.

Two things about `LLMModelUsage` that the field names do not say, both verified
against livekit-agents 1.7.1 rather than assumed:

`input_tokens` is the WHOLE prompt — `metrics/usage.py` accumulates the
plugin's `prompt_tokens`, which the anthropic plugin builds as
`input + cache_creation + cache_read`. The tokens billed at the full input
rate are therefore what is left after subtracting the cached reads and the
cache writes; adding the three rows up bills the same prompt three times.

`provider` is NOT a vendor name. `livekit.plugins.anthropic.LLM.provider`
returns `self._client._base_url.netloc` — the string is `api.anthropic.com`,
and it becomes something else again behind a gateway. So the table is keyed on
the MODEL id, which identifies its vendor on its own and does not move when
the base URL does; the provider is recorded as reported and never matched on.

Open source note: `PRICES` is a plain dict a fork replaces wholesale; nothing
else in the platform knows a currency.
"""

from dataclasses import dataclass

USD_EUR = 0.92  # ECB reference rate, 2026-08; a repricing edits this and the table below
MTOK = 1_000_000


@dataclass(frozen=True)
class TokenPrice:
    """EUR per million tokens for one model, by how the token was billed."""

    input: float
    cached_input: float
    cache_write: float
    output: float


def _usd(input: float, cached: float, write: float, output: float) -> TokenPrice:
    return TokenPrice(input * USD_EUR, cached * USD_EUR, write * USD_EUR, output * USD_EUR)


# Model id as livekit reports it in AgentSessionUsage.model_usage.
PRICES: dict[str, TokenPrice] = {
    # Anthropic list prices, $/Mtok: cache reads are 0.1x input, 5-minute writes 1.25x.
    "claude-haiku-4-5": _usd(1.00, 0.10, 1.25, 5.00),
    "claude-sonnet-5": _usd(2.00, 0.20, 2.50, 10.00),
    # TODO(ms-6): ElevenLabs bills characters and Soniox audio seconds, not tokens.
    # Their rows stay at zero until the voice path exists and the units are real.
    "eleven_v3_conversational": _usd(0, 0, 0, 0),
    "eleven_flash_v2_5": _usd(0, 0, 0, 0),
    "stt-rt-v5": _usd(0, 0, 0, 0),
}


def session_cost(usage) -> dict:
    """The EUR a session's model usage adds up to, with the per-model rows behind it.

    Reads an `AgentSessionUsage`. A model with no row in the table is named in
    `unpriced` and contributes nothing: an unknown price is reported, never
    guessed, and never silently counted as free.
    """
    models, unpriced, total = [], [], 0.0
    for usage_row in getattr(usage, "model_usage", None) or []:
        name = getattr(usage_row, "model", "")
        provider = getattr(usage_row, "provider", "")
        price = PRICES.get(name)
        if price is None:
            unpriced.append(f"{provider}/{name}")
            continue
        eur = _llm_cost(usage_row, price)
        total += eur
        models.append({"provider": provider, "model": name, "eur": round(eur, 6)})
    return {"eur": round(total, 6), "models": models, "unpriced": unpriced}


def _llm_cost(model, price: TokenPrice) -> float:
    """Fresh input, cached reads, cache writes and output, each at its own rate."""
    cached = getattr(model, "input_cached_tokens", 0)
    written = getattr(model, "input_cache_creation_tokens", 0)
    fresh = max(getattr(model, "input_tokens", 0) - cached - written, 0)
    return (
        fresh * price.input
        + cached * price.cached_input
        + written * price.cache_write
        + getattr(model, "output_tokens", 0) * price.output
    ) / MTOK
