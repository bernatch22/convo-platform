"""What a session cost: a price table per provider/model, and the sum over `session.usage`.

Decisions: docs/decisions/convo.observability.prices.md
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
    # OpenAI list prices, $/Mtok (developers.openai.com, checked 2026-08-31): cached input is
    # 0.1x input. There is no cache-WRITE row because there is no such token on this vendor:
    # caching is automatic, the first request pays the plain input rate and
    # `input_cache_creation_tokens` is always 0, so the 0.0 below is a row that never applies
    # rather than a write we believe is free.
    "gpt-5.4-mini": _usd(0.75, 0.075, 0.0, 4.50),
    # TODO(ms-6): ElevenLabs bills characters and Soniox audio seconds, not tokens.
    # Their rows stay at zero until the voice path exists and the units are real.
    "eleven_v3_conversational": _usd(0, 0, 0, 0),
    "eleven_flash_v2_5": _usd(0, 0, 0, 0),
    "stt-rt-v5": _usd(0, 0, 0, 0),
}


def session_cost(usage) -> dict:
    """The EUR a session's model usage adds up to, with the per-model rows behind it."""
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
