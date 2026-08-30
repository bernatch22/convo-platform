"""STT: Soniox stt-rt-v5 with its own semantic endpointing, tuned for a voice agent.

Soniox decides where an utterance ends from the words themselves, not from
silence alone; the three endpoint knobs below are its voice-agent profile
(the API defaults are 0 / 0.0 / 2000 ms and about half a second slower). The
turn detector in `core.providers.turn` is the second opinion; the session
combines both. `context.terms` is the one vocabulary channel the model reads
(`keyterms` is silently ignored), so a project's own words go there.
"""

import os

from livekit.plugins import soniox

from core.context import Project, Tenant

MODEL = "stt-rt-v5"
LANGUAGE_HINTS = ["es", "en"]
SAMPLE_RATE = 16000  # keep 16 kHz even on PSTN: Soniox resamples better than we do
MAX_ENDPOINT_DELAY_MS = 1000
ENDPOINT_LATENCY_ADJUSTMENT_LEVEL = 2
ENDPOINT_SENSITIVITY = 0.3
KEY_ENV = "SONIOX_API_KEY"


def stt_for(tenant: Tenant, project: Project):
    """Soniox for the project's vocabulary, or None without a key (text-only still runs)."""
    key = os.getenv(KEY_ENV)
    if not key:
        return None
    return soniox.STT(api_key=key, params=stt_options(project))


def stt_options(project: Project) -> soniox.STTOptions:
    """The exact options a session sends to Soniox, as data — tests assert on them."""
    return soniox.STTOptions(
        model=MODEL,
        language_hints=list(LANGUAGE_HINTS),
        sample_rate=SAMPLE_RATE,
        max_endpoint_delay_ms=MAX_ENDPOINT_DELAY_MS,
        endpoint_latency_adjustment_level=ENDPOINT_LATENCY_ADJUSTMENT_LEVEL,
        endpoint_sensitivity=ENDPOINT_SENSITIVITY,
        context=soniox.ContextObject(terms=list(project.keyterms)) if project.keyterms else None,
    )
