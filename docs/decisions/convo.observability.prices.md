# `convo.observability.prices`

The reasoning that used to live in the docstrings of `convo/observability/prices.py`; the code keeps one line per symbol.

## module

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

## session_cost

Reads an `AgentSessionUsage`. A model with no row in the table is named in
`unpriced` and contributes nothing: an unknown price is reported, never
guessed, and never silently counted as free.
