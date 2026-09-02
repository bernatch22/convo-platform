"""TTS: ElevenLabs, a conversational v3 voice by default, with word alignment on.

Decisions: docs/decisions/convo.providers.tts.md
"""

import os

from livekit.plugins import elevenlabs

from convo.domain.context import Project, Tenant

DEFAULT_MODEL = "eleven_v3_conversational"
LATENCY_MODEL = "eleven_flash_v2_5"
FORBIDDEN_MODELS = frozenset({"eleven_turbo_v2_5", "eleven_v3"})
KEY_ENV = "ELEVENLABS_API_KEY"


def tts_for(tenant: Tenant, project: Project, voice: str | None = None):
    """ElevenLabs with the project's voice and model, or None without a key."""
    key = os.getenv(KEY_ENV)
    chosen = voice or project.voice
    if not key or not chosen:
        return None
    return elevenlabs.TTS(
        api_key=key,
        voice_id=chosen,
        model=tts_model(project),
        language=project.language.split("-")[0],
        sync_alignment=True,
    )


def tts_model(project: Project) -> str:
    """The project's model, unless it names one the platform refuses to run."""
    wanted = project.tts_model or DEFAULT_MODEL
    return DEFAULT_MODEL if wanted in FORBIDDEN_MODELS else wanted
