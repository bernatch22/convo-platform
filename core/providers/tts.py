"""TTS: ElevenLabs, a conversational v3 voice by default, with word alignment on.

The voice is project data (`Project.voice`), never a constant here: two
projects of one tenant can sound like two people. `eleven_v3_conversational`
is the realtime member of the v3 family; `eleven_v3` itself is not realtime
and `eleven_turbo_v2_5` is deprecated, so neither is ever chosen even when a
project asks. `eleven_flash_v2_5` is the latency profile a project may opt
into. `sync_alignment=True` gives the session timed words for the event log.
"""

import os

from livekit.plugins import elevenlabs

from core.context import Project, Tenant

DEFAULT_MODEL = "eleven_v3_conversational"
LATENCY_MODEL = "eleven_flash_v2_5"
FORBIDDEN_MODELS = frozenset({"eleven_turbo_v2_5", "eleven_v3"})
KEY_ENV = "ELEVENLABS_API_KEY"


def tts_for(tenant: Tenant, project: Project, voice: str | None = None):
    """ElevenLabs with the project's voice and model, or None without a key.

    `voice` overrides the project's for one stage that has its own
    (`Project.stage_voices`) — the model, the language and the alignment stay
    the project's, because a second desk is another person at the same business
    and not another business.
    """
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
