"""STT: a provider slot. Soniox by default, Deepgram Flux as the alternative.

Which one hears the caller is project data (`Project.stt_provider`), like the
voice is — so a supervisor switches ear from the console and the next call
runs on it, no deploy. This module is the dispatch and the two tunings; every
value below is a constant a test can assert on without a network.

Soniox `stt-rt-v5` decides where an utterance ends from the words themselves,
not from silence alone; its three endpoint knobs are the voice-agent profile
(the API defaults are 0 / 0.0 / 2000 ms and about half a second slower).
`context.terms` is the one vocabulary channel the model reads (`keyterms` is
silently ignored), so a project's own words go there.

Deepgram Flux talks a different websocket (`/v2/listen`, the plugin's `STTv2`)
and folds end-of-turn detection into the transcription model itself: instead of
a silence window it emits a turn when it believes the sentence closed, scored
against `eot_threshold`. `flux-general-multi` is the member of the family that
speaks Spanish — `flux-general-en` is English-only and answers a `language_hint`
with a 400 — and Flux takes its vocabulary as `keyterm`, the argument Soniox
ignores.

The turn detector in `core.providers.turn` is the second opinion either way;
the session combines both.
"""

import os

from livekit.plugins import deepgram, soniox

from core.context import Project, Tenant

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


def stt_for(tenant: Tenant, project: Project):
    """The STT the project chose, or None when its key is absent (text-only still runs)."""
    if provider_for(project) == DEEPGRAM:
        return deepgram_stt(tenant, project)
    return soniox_stt(tenant, project)


def provider_for(project: Project) -> str:
    """The provider that will really run: the project's, unless it names one we do not have.

    Same rule as `core.providers.tts.tts_model`: unknown data falls back to the
    platform default instead of failing a call. The control plane refuses to
    store an unknown provider in the first place (`core.pipeline.overridable`).
    """
    return project.stt_provider if project.stt_provider in PROVIDERS else SONIOX


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
    """The exact keyword arguments a session builds `STTv2` with — tests assert on them.

    `STTv2` has no options object of its own the caller can hand it (its
    `STTOptions` carries the endpoint url too), so the tuning travels as this
    dict and both the factory and the console read the same one.
    """
    return {
        "model": DEEPGRAM_MODEL,
        "sample_rate": DEEPGRAM_SAMPLE_RATE,
        "language_hint": list(DEEPGRAM_LANGUAGE_HINTS),
        "eot_threshold": DEEPGRAM_EOT_THRESHOLD,
        "eot_timeout_ms": DEEPGRAM_EOT_TIMEOUT_MS,
        "keyterm": list(project.keyterms),
    }
