"""Provider factories: the only place that knows which vendor backs each capability."""

import os

import anthropic as anthropic_sdk
from livekit.plugins import anthropic

from core.context import Project, Tenant

HAIKU = "claude-haiku-4-5"


def llm_for(tenant: Tenant):
    """Claude Haiku with prompt caching for every tenant (Sonnet is measured in evals only)."""
    return anthropic.LLM(
        model=HAIKU,
        caching="ephemeral",
        max_tokens=300,
        api_key=os.environ["ANTHROPIC_API_KEY"],
        client=_anthropic_client(),
    )


def stt_for(tenant: Tenant):
    """Speech-to-text arrives in ms-6 (Soniox); until then sessions are text-only."""
    return None


def tts_for(tenant: Tenant, project: Project):
    """Text-to-speech arrives in ms-6 (ElevenLabs); until then sessions are text-only."""
    return None


def _anthropic_client() -> anthropic_sdk.AsyncClient | None:
    """Identity-linked keys must name their workspace; plain keys need no custom client."""
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID")
    if not workspace:
        return None
    return anthropic_sdk.AsyncClient(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        default_headers={"anthropic-workspace-id": workspace},
    )
