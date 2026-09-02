# `convo.providers.llm`

The reasoning that used to live in the docstrings of `convo/providers/llm.py`; the code keeps one line per symbol.

## module

The model is project data (`Project.llm_model`), overridable from the console
like the voice and the TTS model — the LLM is a swappable interface driver, and
a platform that can only run one vendor cannot prove that claim. `llm_for`
dispatches on the model name's FAMILY, because the name identifies its vendor
on its own: `claude-*` builds the anthropic plugin exactly as it always did,
`gpt-*` builds the openai one.

`ALLOWED_MODELS` is short on purpose and it is not a suggestion. A model the
platform runs is a model somebody priced (`core.observability.prices`) and
measured; a PUT naming anything else is a 422 that lists these two, and a
project whose git names something else falls back to the default rather than
opening a connection nobody costed.

Being on the list is half of it: the box also has to carry the vendor's key.
`KEY_ENV` names where each family's key lives, `runnable` asks whether this
host has it, and `llm_model` treats a missing one as unusable config — the
same fall-back-to-the-default rule the allow-list already had. It is written
down because the absence cost us a morning: on 2026-08-31 the console stored
`llm_model=gpt-5.4-mini` on a box with no `OPENAI_API_KEY` and every job died
with a `KeyError` here until somebody read a worker log. The control plane now
refuses that override at the door (`core.pipeline.overridable`) AND the worker
survives one already stored. Only the variable NAME is ever printed.

The two families do not cache the same way and the difference is not cosmetic:

- Anthropic caching is EXPLICIT (`caching="ephemeral"`) and Haiku 4.5 only
  caches a prefix from 4096 tokens up — below that the flag is a silent no-op.
- OpenAI caching is AUTOMATIC from 1024 tokens up, with no flag to set. What we
  do set is `prompt_cache_key`: it routes requests that share a prefix to the
  same cache shard, so a busy fleet keeps hitting the warm one. It is
  `tenant/project` — stable for the life of a deploy, never a timestamp or a
  request id, for the same reason the system prompt carries neither.

Both plugins hand `ChatContext` to the framework's own
`llm/_provider_format/{anthropic,openai}.py`, and BOTH of those call
`group_tool_calls()`, which drops a `function_call` with no output and an
output with no call before the request is built (verified in
livekit-agents 1.7.1). That is the orphan-`tool_use` sanitation CLAUDE.md asks
for, it lives one layer below us, and it is provider-independent: neither
family needs a `sanitize_tool_pairing` call of our own, and adding one on the
openai path would duplicate work the framework already did.

## llm_model

Two things stand between the project's choice and the connection. The
allow-list is the first: a model nobody priced is never opened, however git
names it. The host is the second, and it is the one that used to end calls
rather than start them — an override stored from a console can name a
vendor whose key this box does not carry, and taking it as gospel meant a
`KeyError` in the middle of every job. Unusable config falls back to the
default here exactly as it always has; a key the box lacks is unusable
config, not an emergency.

## _openai

`max_completion_tokens` is the openai plugin's name for what the anthropic
one calls `max_tokens`. The plugin sets `reasoning_effort="none"` for this
model on its own — a reasoning pass before every spoken answer is latency a
caller hears — so we do not pass one.

## _warn_if_swapped

Only the keyless case earns a line: a model outside the allow-list is a
deploy-time mistake the console already shows, while a key absent from THIS
box is an operational fact nobody can see from there.
