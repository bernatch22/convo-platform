"""The pipeline as data: what the three providers are set to do for one project.

Decisions: docs/decisions/convo.session.pipeline.md
"""

import statistics
from typing import Any

from convo.domain.context import Project, Tenant
from convo.observability.observers import TURN_METRICS
from convo.providers import llm, stt, tts
from convo.state.overrides import OVERRIDABLE
from convo.state.store import Store
from convo.telephony import human, lines

# How many of a project's stored voice sessions the medians are measured over.
LATENCY_SESSIONS = 20

# Haiku 4.5 is the whole reason a project prefix has to be long: below the
# threshold `caching="ephemeral"` is a silent no-op, not an error. The two
# families cache differently enough that one sentence would lie about one of
# them, so the note is chosen by family in `llm_view`.
CACHE_NOTES = {
    "anthropic": (
        f"{llm.HAIKU} caches a prompt prefix only from 4096 tokens up (Sonnet caches from "
        "1024). Below that the ephemeral cache is a silent no-op: keep the system prompt, the "
        "tool definitions and the policy block above 4096 tokens, byte-identical between turns."
    ),
    "openai": (
        f"{llm.GPT_MINI} caches automatically from 1024 tokens up — there is no flag to set "
        "and no cache-write token to pay for. The prefix must still be byte-identical between "
        "turns; `prompt_cache_key` is set to tenant/project so requests that share a prefix "
        "keep landing on the same warm shard."
    ),
}

TURN_KINDS = ("turn.agent", "turn.user")


def snapshot(tenant: Tenant, project: Project, store: Store) -> dict[str, Any]:
    """Everything the pipeline screen shows for one project: providers, overrides, latencies."""
    return {
        "tenant": tenant.id,
        "project": project.id,
        "name": project.name,
        "language": project.language,
        "greeting": project.greeting,
        "stt": stt_view(project),
        "llm": llm_view(project),
        "tts": tts_view(project),
        "phone": {**lines.view(store, tenant.id, project.id), "transfer": human.view(project)},
        "overrides": [
            {"field": o.field, "value": o.value, "updated_at": o.updated_at}
            for o in store.pipeline_overrides(tenant.id, project.id)
        ],
        "overridable": list(OVERRIDABLE),
        "latency": latency(store, tenant.id, project.id),
    }


def stt_view(project: Project) -> dict[str, Any]:
    """The chosen ear as configured — its own model and knobs — and what it could be switched to."""
    chosen = stt.provider_for(project)
    view = _soniox_view(project) if chosen == stt.SONIOX else _deepgram_view(project)
    view["requested_provider"] = project.stt_provider
    view["providers"] = list(stt.PROVIDERS)
    view["unavailable_reasons"] = _unavailable("stt_provider", stt.PROVIDERS)
    return view


def llm_view(project: Project) -> dict[str, Any]:
    """The model the next session will really build, its family's caching story, the whole menu."""
    model = llm.llm_model(project)
    kind = llm.family(model)
    return {
        "provider": kind,
        "model": model,
        "requested_model": project.llm_model,
        "default_model": llm.DEFAULT_MODEL,
        "allowed_models": list(llm.ALLOWED_MODELS),
        "caching": "ephemeral" if kind == "anthropic" else "automatic",
        "max_tokens": llm.MAX_TOKENS,
        "cache_minimum_tokens": llm.CACHE_FLOOR[kind],
        "cache_note": CACHE_NOTES[kind],
        "unavailable_reasons": _unavailable("llm_model", llm.ALLOWED_MODELS),
    }


def tts_view(project: Project) -> dict[str, Any]:
    """ElevenLabs: the model the platform will really run, the voice, and what it refuses."""
    return {
        "provider": "elevenlabs",
        "model": tts.tts_model(project),
        "requested_model": project.tts_model,
        "default_model": tts.DEFAULT_MODEL,
        "latency_model": tts.LATENCY_MODEL,
        "forbidden_models": sorted(tts.FORBIDDEN_MODELS),
        "forbidden_reasons": {
            model: overridable("tts_model", model) for model in sorted(tts.FORBIDDEN_MODELS)
        },
        "voice": project.voice,
        "sync_alignment": True,
    }


def latency(store: Store, tenant: str, project: str, limit: int = LATENCY_SESSIONS) -> dict:
    """Median ttft / e2e / end-of-turn / transcription delay over the last voice sessions."""
    rows = [
        row
        for row in store.sessions()
        if (row.tenant, row.project, row.channel) == (tenant, project, "voice")
    ][:limit]
    samples: dict[str, list[float]] = {key: [] for key in TURN_METRICS}
    turns = 0
    for row in rows:
        for event in store.events(row.id):
            if event.kind not in TURN_KINDS:
                continue
            turns += 1
            for key, value in (event.payload.get("metrics") or {}).items():
                if key in samples and isinstance(value, (int, float)):
                    samples[key].append(float(value))
    medians = {k: round(statistics.median(v), 3) if v else None for k, v in samples.items()}
    return {"sessions": len(rows), "turns": turns, "medians": medians}


def running(project: Project, channel: str) -> dict[str, Any]:
    """The four provider choices this session really runs on, small enough for one event."""
    audible = channel == "voice"
    return {
        "voice": project.voice if audible else None,
        "tts_model": tts.tts_model(project) if audible else None,
        "stt_provider": stt.provider_for(project) if audible else None,
        "llm_model": llm.llm_model(project),
    }


def cleaned(field: str, value: str) -> str:
    """The value as it will be stored: an id loses its stray whitespace, a greeting keeps it."""
    return value if field == "greeting" else value.strip()


def overridable(field: str, value: str) -> str | None:
    """Why this override is refused, or None when the platform will run it."""
    if field not in OVERRIDABLE:
        return f"{field!r} is not overridable; the console may set {list(OVERRIDABLE)}"
    if field == "voice" and not value:
        return (
            "an empty voice id is not a voice: `tts_for` cannot tell one from a missing "
            "ELEVENLABS_API_KEY, so it builds no TTS at all and the next call comes up mute "
            "while the worker log blames a key that is present. Name an ElevenLabs voice id — "
            "the console's escape hatch stores whatever you type, but not nothing."
        )
    if field == "llm_model" and value not in llm.ALLOWED_MODELS:
        return (
            f"{value!r} is not a model this platform runs: the allowed models are "
            f"{list(llm.ALLOWED_MODELS)}. Every one of them is priced in "
            "core/observability/prices.py and measured in the evals; an unpriced model would "
            "spend money no session report could account for."
        )
    if field == "tts_model" and value in tts.FORBIDDEN_MODELS:
        return (
            f"{value!r} is refused by the platform: {sorted(tts.FORBIDDEN_MODELS)} never run "
            "(eleven_v3 is not realtime, eleven_turbo_v2_5 is deprecated). "
            f"Use {tts.DEFAULT_MODEL!r} or {tts.LATENCY_MODEL!r}."
        )
    if field == human.FIELD:
        return human.refusal(value)
    if field == "stt_provider" and value not in stt.PROVIDERS:
        return (
            f"{value!r} is not an STT provider this platform runs: "
            f"the console may choose {list(stt.PROVIDERS)}."
        )
    if field == "llm_model" and not llm.runnable(value):
        other = f"the default model {llm.DEFAULT_MODEL!r}" if value != llm.DEFAULT_MODEL else None
        return _absent(value, llm.key_env(value), other)
    if field == "stt_provider" and not stt.runnable(value):
        other = f"the default ear {stt.SONIOX!r}" if value != stt.SONIOX else None
        return _absent(value, stt.key_env(value), other)
    return None


def _unavailable(field: str, values: tuple[str, ...]) -> dict[str, str]:
    """The choices this host cannot open, each with the sentence a PUT would be refused with."""
    refusals = {value: overridable(field, value) for value in values}
    return {value: why for value, why in refusals.items() if why}


def _absent(value: str, variable: str, fallback: str | None) -> str:
    """The refusal for a provider this host has no key for — the variable, never its value."""
    said = (
        f"{value!r} needs {variable} on this host and the box carries none: the variable is "
        f"not set in the worker's environment. Nothing here reads its contents."
    )
    if fallback is None:
        return f"{said} It is the platform default, so put it in the fleet's env and restart."
    return (
        f"{said} Put it there and restart the fleet, or leave this project on {fallback}: "
        f"stored now, every session would quietly fall back to it anyway, with a warning "
        f"nobody reading this console would ever see."
    )


def _soniox_view(project: Project) -> dict[str, Any]:
    """Soniox as configured: model, hints, the three endpointing knobs, the project's terms."""
    return {
        "provider": stt.SONIOX,
        "model": stt.MODEL,
        "language_hints": list(stt.LANGUAGE_HINTS),
        "sample_rate": stt.SAMPLE_RATE,
        "endpointing": {
            "max_endpoint_delay_ms": stt.MAX_ENDPOINT_DELAY_MS,
            "latency_adjustment_level": stt.ENDPOINT_LATENCY_ADJUSTMENT_LEVEL,
            "sensitivity": stt.ENDPOINT_SENSITIVITY,
        },
        "keyterms": list(project.keyterms),
    }


def _deepgram_view(project: Project) -> dict[str, Any]:
    """Deepgram Flux as configured: the multilingual model, its two turn scores, the terms."""
    options = stt.deepgram_options(project)
    return {
        "provider": stt.DEEPGRAM,
        "model": options["model"],
        "language_hints": list(options["language_hint"]),
        "sample_rate": options["sample_rate"],
        "endpointing": {
            "eot_threshold": options["eot_threshold"],
            "eot_timeout_ms": options["eot_timeout_ms"],
            "eager_eot_threshold": None,  # preemptive generation is off by decision
        },
        "keyterms": list(options["keyterm"]),
    }
