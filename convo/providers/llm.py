"""LLM: a provider slot. Claude Haiku 4.5 by default, GPT-5.4-mini when a project asks.

Decisions: docs/decisions/convo.providers.llm.md
"""

import logging
import os

import anthropic as anthropic_sdk
from livekit.plugins import anthropic, openai

from convo.domain.context import Project, Tenant

log = logging.getLogger("platform.llm")

HAIKU = "claude-haiku-4-5"
GPT_MINI = "gpt-5.4-mini"
DEFAULT_MODEL = HAIKU

# Exactly what the platform will run: each of these is priced and measured.
ALLOWED_MODELS = (HAIKU, GPT_MINI)

# Where each family's key lives on the box. The NAME travels — into a refusal,
# into a warning, into the console; the VALUE never leaves this module.
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}

MAX_TOKENS = 300

# Where each family's caching becomes real. Below it the cache is a no-op.
CACHE_FLOOR = {"anthropic": 4096, "openai": 1024}


def llm_for(tenant: Tenant, project: Project):
    """The project's model, built by its family: Claude with caching, or GPT-5.4-mini."""
    model = llm_model(project)
    _warn_if_swapped(project, model)
    if not runnable(model):
        raise RuntimeError(f"{model} needs {key_env(model)} and this host carries none")
    if family(model) == "openai":
        return _openai(tenant, project, model)
    return _anthropic(model)


def llm_model(project: Project) -> str:
    """The model the next session on THIS host will really build."""
    wanted = project.llm_model or DEFAULT_MODEL
    if wanted not in ALLOWED_MODELS:
        return DEFAULT_MODEL
    return wanted if runnable(wanted) else DEFAULT_MODEL


def family(model: str) -> str:
    """Which vendor a model id belongs to — the name says it, no lookup table needed."""
    return "openai" if model.startswith("gpt-") else "anthropic"


def key_env(model: str) -> str:
    """The environment variable this model's vendor key must live in on the box."""
    return KEY_ENV[family(model)]


def runnable(model: str) -> bool:
    """Whether this host carries the key this model needs — the name, never the value."""
    return bool(os.getenv(key_env(model)))


def _anthropic(model: str):
    """Claude with explicit ephemeral caching; the prefix has to clear 4096 tokens."""
    return anthropic.LLM(
        model=model,
        caching="ephemeral",
        max_tokens=MAX_TOKENS,
        api_key=os.environ[KEY_ENV["anthropic"]],
        client=_anthropic_client(),
    )


def _openai(tenant: Tenant, project: Project, model: str):
    """GPT with automatic prefix caching, pinned to one cache shard per project."""
    return openai.LLM(
        model=model,
        api_key=os.environ[KEY_ENV["openai"]],
        max_completion_tokens=MAX_TOKENS,
        prompt_cache_key=f"{tenant.id}/{project.id}",
    )


def _warn_if_swapped(project: Project, model: str) -> None:
    """One line per built session when a priced model was swapped for want of a key."""
    wanted = project.llm_model or DEFAULT_MODEL
    if wanted == model or wanted not in ALLOWED_MODELS:
        return
    log.warning(
        "llm: %s needs %s and this host carries none; running %s instead",
        wanted,
        key_env(wanted),
        model,
    )


def _anthropic_client() -> anthropic_sdk.AsyncClient | None:
    """Identity-linked keys must name their workspace; plain keys need no custom client."""
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID")
    if not workspace:
        return None
    return anthropic_sdk.AsyncClient(
        api_key=os.environ[KEY_ENV["anthropic"]],
        default_headers={"anthropic-workspace-id": workspace},
    )
