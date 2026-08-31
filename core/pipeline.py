"""The pipeline as data: what the three providers are set to do for one project.

Nobody should have to read `core/providers/*.py` to know which Soniox model
answers a call, whether the prompt is cached, or which voice speaks. This
module turns those constants — plus the project's own voice, model and
greeting, and the latencies its last calls actually measured — into one dict
the console renders and a test can assert on.

It is a READ of the platform's own configuration: every value here is either a
constant from `core.providers`, project data, or a median over stored events.
Nothing is invented and nothing is defaulted silently — a project that has
never run answers with `null` medians, never with a zero.

The write half is `overridable`: the fields the console may set, and the rules
that refuse a value the platform will not run.
"""

import statistics
from typing import Any

from core.context import Project, Tenant
from core.observability.observers import TURN_METRICS
from core.providers import llm, stt, tts
from core.state.overrides import OVERRIDABLE
from core.state.store import Store

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
        "overrides": [
            {"field": o.field, "value": o.value, "updated_at": o.updated_at}
            for o in store.pipeline_overrides(tenant.id, project.id)
        ],
        "overridable": list(OVERRIDABLE),
        "latency": latency(store, tenant.id, project.id),
    }


def stt_view(project: Project) -> dict[str, Any]:
    """The chosen ear as configured — its own model and knobs — and what it could be switched to.

    `endpointing` is the chosen provider's own dial set, not a common
    denominator: Soniox holds a turn open for a silence window, Flux scores its
    belief that the sentence closed. Flattening the two into shared keys would
    invent a knob neither provider has, so the console branches on `provider`.
    """
    chosen = stt.provider_for(project)
    view = _soniox_view(project) if chosen == stt.SONIOX else _deepgram_view(project)
    view["requested_provider"] = project.stt_provider
    view["providers"] = list(stt.PROVIDERS)
    return view


def llm_view(project: Project) -> dict[str, Any]:
    """The model the next session will really build, its family's caching story, the whole menu.

    `requested_model` is what the project asked for and `model` is what runs:
    they differ only when git names a model outside `ALLOWED_MODELS`, which
    `llm_model()` falls back on rather than opening a connection nobody priced.
    """
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
    }


def tts_view(project: Project) -> dict[str, Any]:
    """ElevenLabs: the model the platform will really run, the voice, and what it refuses.

    `forbidden_reasons` carries the very sentence `overridable` would answer a
    PUT with, so the console can grey a model out and say why in the server's
    words instead of keeping its own copy of the rule.
    """
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
    """Median ttft / e2e / end-of-turn / transcription delay over the last voice sessions.

    Medians, not averages: one 9-second turn where a tool waited on a slow
    adapter says nothing about what the caller usually hears. `null` means the
    turns carry no such measurement — a text session has no `tts_node_ttfb`,
    and a project nobody has called has nothing at all.
    """
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


def overridable(field: str, value: str) -> str | None:
    """Why this override is refused, or None when the platform will run it.

    Two rules. The TTS one the platform has always enforced: `eleven_v3` is not
    realtime and `eleven_turbo_v2_5` is deprecated, so neither may be stored —
    `tts_model()` would silently ignore them at build time and the console would
    show a model the caller never hears. The LLM one is an allow-list rather
    than a deny-list: a model the platform runs is one somebody priced and
    measured, so "may I run X" is no unless X is one of the two, and the
    refusal names them both. The STT one is the same shape: only the providers
    in `core.providers.stt.PROVIDERS` have a factory, so any other name would
    fall back to Soniox and the console would show an ear the caller is not on.
    """
    if field not in OVERRIDABLE:
        return f"{field!r} is not overridable; the console may set {list(OVERRIDABLE)}"
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
    if field == "stt_provider" and value not in stt.PROVIDERS:
        return (
            f"{value!r} is not an STT provider this platform runs: "
            f"the console may choose {list(stt.PROVIDERS)}."
        )
    return None


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
