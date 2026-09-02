"""STT: a provider slot. Soniox by default, Deepgram Flux as the alternative.

Decisions: docs/decisions/convo.providers.stt.md
"""

import logging
import os

from livekit.plugins import deepgram, soniox

from convo.domain.context import Project, Tenant

log = logging.getLogger("platform.stt")

SONIOX = "soniox"
DEEPGRAM = "deepgram"
PROVIDERS = (SONIOX, DEEPGRAM)

# --- Soniox (the default) ----------------------------------------------------

MODEL = "stt-rt-v5"
LANGUAGE_HINTS = ["es", "en"]
SAMPLE_RATE = 16000  # keep 16 kHz even on PSTN: Soniox resamples better than we do
MAX_ENDPOINT_DELAY_MS = 1000
ENDPOINT_LATENCY_ADJUSTMENT_LEVEL = 2
ENDPOINT_SENSITIVITY = 0.3
KEY_ENV = "SONIOX_API_KEY"

# --- Deepgram Flux -----------------------------------------------------------

DEEPGRAM_MODEL = "flux-general-multi"  # the multilingual Flux; -en refuses a language hint
DEEPGRAM_LANGUAGE_HINTS = ["es", "en"]
DEEPGRAM_SAMPLE_RATE = 16000
DEEPGRAM_EOT_THRESHOLD = 0.7  # how sure Flux must be the sentence closed (0.5–0.9)
DEEPGRAM_EOT_TIMEOUT_MS = 1000  # the hard stop, matching Soniox's max endpoint delay
DEEPGRAM_KEY_ENV = "DEEPGRAM_API_KEY"

# Where each ear's key lives on the box. The NAME travels — into a refusal,
# into a warning, into the console; the VALUE never leaves this module.
KEY_ENV_FOR = {SONIOX: KEY_ENV, DEEPGRAM: DEEPGRAM_KEY_ENV}


def stt_for(tenant: Tenant, project: Project):
    """The ear the project chose, or the default one when this box has no key for it."""
    provider = provider_for(project)
    _warn_if_swapped(project, provider)
    if provider == DEEPGRAM:
        return deepgram_stt(tenant, project)
    return soniox_stt(tenant, project)


def provider_for(project: Project) -> str:
    """The ear that will really run: the project's, unless this host cannot open it."""
    wanted = project.stt_provider
    if wanted not in PROVIDERS:
        return SONIOX
    return wanted if runnable(wanted) else SONIOX


def key_env(provider: str) -> str:
    """The environment variable this provider's key must live in on the box."""
    return KEY_ENV_FOR[provider]


def runnable(provider: str) -> bool:
    """Whether this host carries the key this ear needs — the name, never the value."""
    return provider in KEY_ENV_FOR and bool(os.getenv(key_env(provider)))


def soniox_stt(tenant: Tenant, project: Project):
    """Soniox for the project's vocabulary, or None without a key."""
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


def deepgram_stt(tenant: Tenant, project: Project):
    """Deepgram Flux for the project's vocabulary, or None without a key."""
    key = os.getenv(DEEPGRAM_KEY_ENV)
    if not key:
        return None
    return deepgram.STTv2(api_key=key, **deepgram_options(project))


def deepgram_options(project: Project) -> dict:
    """The exact keyword arguments a session builds `STTv2` with — tests assert on them."""
    return {
        "model": DEEPGRAM_MODEL,
        "sample_rate": DEEPGRAM_SAMPLE_RATE,
        "language_hint": list(DEEPGRAM_LANGUAGE_HINTS),
        "eot_threshold": DEEPGRAM_EOT_THRESHOLD,
        "eot_timeout_ms": DEEPGRAM_EOT_TIMEOUT_MS,
        "keyterm": list(project.keyterms),
    }


def _warn_if_swapped(project: Project, provider: str) -> None:
    """One line per built session when the chosen ear was swapped for want of a key."""
    wanted = project.stt_provider
    if wanted == provider or wanted not in PROVIDERS:
        return
    log.warning(
        "stt: %s needs %s and this host carries none; listening with %s instead",
        wanted,
        key_env(wanted),
        provider,
    )
