"""The three fields a supervisor may change between calls, without a deploy."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from convo.api.deps import Reader, effective
from convo.session import pipeline
from convo.state import overrides
from convo.state.store import PipelineOverride

router = APIRouter()


class PipelineUpdate(BaseModel):
    """The fields the console may change between calls; anything else is refused."""

    model_config = ConfigDict(extra="forbid")

    voice: str | None = None
    tts_model: str | None = None
    greeting: str | None = None
    stt_provider: str | None = None
    llm_model: str | None = None
    # E.164, or "" to take the handover verb away from the agent entirely.
    transfer_number: str | None = None


@router.get("/pipeline/{tenant}/{project}")
async def pipeline_view(tenant: str, project: str, store: Reader) -> dict[str, Any]:
    """The three providers as data, plus what the console changed and what calls measured.

    → `{"tenant", "project", "name", "language", "greeting",
        "stt": {"provider", "requested_provider", "providers", "model", "language_hints",
                "sample_rate", "endpointing": "<the CHOSEN provider's own knobs>", "keyterms"},
        "llm": {"provider", "model", "requested_model", "default_model", "allowed_models",
                "caching", "max_tokens", "cache_minimum_tokens", "cache_note"},
        "tts": {"provider", "model", "requested_model", "default_model", "latency_model",
                "forbidden_models", "forbidden_reasons", "voice", "sync_alignment"},
        "phone": {"fleet": str, "note": str,
                  "lines": [{"number", "fleet", "channel", "serving": bool}],
                  "transfer": {"tool", "number", "declared": bool, "offered": bool,
                               "unavailable_reasons": {tool: why}, "note": str}},
        "overrides": [{"field", "value", "updated_at"}], "overridable": [str],
        "latency": {"sessions": int, "turns": int,
                    "medians": {"transcription_delay", "end_of_turn_delay", "llm_node_ttft",
                                "tts_node_ttfb", "e2e_latency"}}}`

    Every value is what the NEXT session will use: the overrides are already
    applied to `greeting`, `tts.model` and `tts.voice`. A median is null when
    no stored voice session measured it.

    `phone` is the store's `routes` table read for THIS project, never for the
    fleet: `lines` is empty for a project nobody can call, and `note` says so
    in the words the screen prints. `serving` is false for a number registered
    against another fleet — it exists, and no call on it arrives here.

    `phone.transfer` is the other direction: where the AGENT may hand a call
    when the caller asks for a person. `offered` false means the model is never
    shown the verb at all, and `unavailable_reasons` carries the sentence saying
    which half is missing — the project's opt-in, or the number.
    """
    known, project_ = effective(tenant, project, store)
    return pipeline.snapshot(known, project_, store)


@router.put("/pipeline/{tenant}/{project}")
async def pipeline_set(
    tenant: str, project: str, update: PipelineUpdate, store: Reader
) -> dict[str, Any]:
    """Change an overridable pipeline field for the next session — no deploy, no restart.

    Returns the same object as `GET /pipeline/{tenant}/{project}`, already
    reflecting the change, so the console renders one response instead of
    refetching. A TTS model the platform refuses to run (`eleven_v3`,
    `eleven_turbo_v2_5`) is a 422 naming the rule, an `llm_model` outside the
    allow-list is a 422 naming the list, an STT provider that is not
    `soniox` or `deepgram` is a 422 too, and a `transfer_number` that is not
    E.164 is a 422 naming the shape a SIP REFER can carry; an unknown field is
    a 422 from the body itself; a body that sets nothing is a 422 too. An empty
    `voice` is a 422 as well: nothing downstream refuses it — `tts_for` absorbs
    it as "no voice configured" and the next call is mute — so the rule lives
    here. An empty `transfer_number` is the opposite and is stored: it is how
    the console takes the handover verb away from the agent.
    Every value but the greeting is stripped before it is judged and stored.

    One 422 is about the BOX, not the value: this process runs where the worker
    runs, so a provider slot whose vendor key is absent from the environment is
    refused here, naming the variable that would have to exist — an override
    the fleet cannot honour is caught at the door instead of by a dead call.
    """
    edits = {
        name: pipeline.cleaned(name, value)
        for name, value in update.model_dump(exclude_none=True).items()
    }
    if not edits:
        raise HTTPException(422, f"set at least one of {list(overrides.OVERRIDABLE)}")
    known, _ = effective(tenant, project, store)
    for name, value in edits.items():
        refusal = pipeline.overridable(name, value)
        if refusal:
            raise HTTPException(422, refusal)
    for name, value in edits.items():
        store.set_pipeline_override(PipelineOverride(tenant, project, name, value))
    _, project_ = effective(tenant, project, store)
    return pipeline.snapshot(known, project_, store)
