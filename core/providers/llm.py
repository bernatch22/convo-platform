"""LLM: Claude Haiku 4.5 with prompt caching, for every tenant."""

import os

import anthropic as anthropic_sdk
from livekit.plugins import anthropic

from core.context import Tenant

HAIKU = "claude-haiku-4-5"
MAX_TOKENS = 300


def llm_for(tenant: Tenant):
    """Claude Haiku with prompt caching for every tenant (Sonnet is measured in evals only)."""
    return anthropic.LLM(
        model=HAIKU,
        caching="ephemeral",
        max_tokens=MAX_TOKENS,
        api_key=os.environ["ANTHROPIC_API_KEY"],
        client=_anthropic_client(),
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
