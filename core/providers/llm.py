"""LLM: a provider slot. Claude Haiku 4.5 by default, GPT-5.4-mini when a project asks.

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
"""

import os

import anthropic as anthropic_sdk
from livekit.plugins import anthropic, openai

from core.context import Project, Tenant

HAIKU = "claude-haiku-4-5"
GPT_MINI = "gpt-5.4-mini"
DEFAULT_MODEL = HAIKU

# Exactly what the platform will run: each of these is priced and measured.
ALLOWED_MODELS = (HAIKU, GPT_MINI)

MAX_TOKENS = 300

# Where each family's caching becomes real. Below it the cache is a no-op.
CACHE_FLOOR = {"anthropic": 4096, "openai": 1024}


def llm_for(tenant: Tenant, project: Project):
    """The project's model, built by its family: Claude with caching, or GPT-5.4-mini."""
    model = llm_model(project)
    if family(model) == "openai":
        return _openai(tenant, project, model)
    return _anthropic(model)


def llm_model(project: Project) -> str:
    """The project's model, unless it names one the platform will not run."""
    wanted = project.llm_model or DEFAULT_MODEL
    return wanted if wanted in ALLOWED_MODELS else DEFAULT_MODEL


def family(model: str) -> str:
    """Which vendor a model id belongs to — the name says it, no lookup table needed."""
    return "openai" if model.startswith("gpt-") else "anthropic"


def _anthropic(model: str):
    """Claude with explicit ephemeral caching; the prefix has to clear 4096 tokens."""
    return anthropic.LLM(
        model=model,
        caching="ephemeral",
        max_tokens=MAX_TOKENS,
        api_key=os.environ["ANTHROPIC_API_KEY"],
        client=_anthropic_client(),
    )


def _openai(tenant: Tenant, project: Project, model: str):
    """GPT with automatic prefix caching, pinned to one cache shard per project.

    `max_completion_tokens` is the openai plugin's name for what the anthropic
    one calls `max_tokens`. The plugin sets `reasoning_effort="none"` for this
    model on its own — a reasoning pass before every spoken answer is latency a
    caller hears — so we do not pass one.
    """
    return openai.LLM(
        model=model,
        api_key=os.environ["OPENAI_API_KEY"],
        max_completion_tokens=MAX_TOKENS,
        prompt_cache_key=f"{tenant.id}/{project.id}",
    )


def _anthropic_client() -> anthropic_sdk.AsyncClient | None:
    """Identity-linked keys must name their workspace; plain keys need no custom client."""
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID")
    if not workspace:
        return None
    return anthropic_sdk.AsyncClient(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        default_headers={"anthropic-workspace-id": workspace},
    )
