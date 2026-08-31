"""Control plane: the HTTP door a client knocks on before any room exists.

The worker (`worker.py`) never opens a database or takes a business decision;
this process does. It mints session tokens with the agent dispatch inside
them, says what this deploy serves, hands the console every stored session,
and stores the three pipeline fields a supervisor may change without a deploy.
Run it with:

    uv run uvicorn api:app --port 8090

The handlers are thin on purpose: `core.control_plane` holds the read side and
`core.pipeline` the provider snapshot, so both are testable without HTTP. Each
route's docstring documents the exact JSON it returns — the web client writes
its TypeScript types from these and nothing else.

Every handler is `async` and opens its own store. SQLite hands out a
connection bound to the thread that created it, and a sync handler runs in a
worker thread while an SSE generator runs in the event loop: one store per
request, created and used in one place, is the whole of the concurrency story.
"""

from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from core import control_plane, pipeline, rooms
from core.auth import mint_observer, mint_session
from core.context import Project, Tenant
from core.contracts import Channel, SessionMeta
from core.registry import load_registry
from core.rooms import RoomsUnreachable
from core.state import overrides
from core.state.store import PipelineOverride, SQLiteStore, Store
from core.webui import mount_ui

app = FastAPI(title="convo control plane")

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def open_store() -> Store:
    """One store per request, opened in the coroutine that reads it (see the module docstring)."""
    return SQLiteStore()


# The store every handler reads, injected so a test can seed a MemoryStore.
Reader = Annotated[Store, Depends(open_store)]


class TokenRequest(BaseModel):
    """What a client must say to open a session: who it wants to talk to, and how."""

    tenant: str
    project: str
    channel: Channel = "chat"
    user_id: str = "anonymous"


class ObserveRequest(BaseModel):
    """The one thing a supervisor must name to listen in: the room, exactly."""

    model_config = ConfigDict(extra="forbid")

    room: str


class PipelineUpdate(BaseModel):
    """The three fields the console may change between calls; anything else is refused.

    `extra="forbid"`: a typo like `ttsModel` must come back as a 422 naming the
    field, not be stored as an override nothing will ever read.
    """

    model_config = ConfigDict(extra="forbid")

    voice: str | None = None
    tts_model: str | None = None
    greeting: str | None = None


@app.post("/token")
def token(req: TokenRequest) -> dict[str, str]:
    """Validate the tenant/project against the registry and mint the session ticket.

    → `{"token": "<jwt>", "room": "<tenant>-<project>-<uuid>", "url": "<livekit ws url>"}`
    """
    registry = load_registry()
    tenant = registry.get(req.tenant)
    if tenant is None:
        raise HTTPException(404, f"unknown tenant {req.tenant!r}; known: {sorted(registry)}")
    if req.project not in tenant.projects:
        known = sorted(tenant.projects)
        detail = f"tenant {req.tenant!r} has no project {req.project!r}; known: {known}"
        raise HTTPException(404, detail)
    meta = SessionMeta(tenant=req.tenant, project=req.project, channel=req.channel)
    return mint_session(meta, user_id=req.user_id)


@app.get("/tenants")
def tenants() -> list[dict]:
    """What this deployment serves: every routable tenant and its projects.

    → `[{"tenant": str, "projects": [{"id", "name", "voice", "language"}]}]`
    """
    return [
        {
            "tenant": tenant.id,
            "projects": [
                {"id": p.id, "name": p.name, "voice": p.voice, "language": p.language}
                for p in tenant.projects.values()
            ],
        }
        for tenant in load_registry().values()
    ]


@app.get("/sessions")
async def sessions(
    store: Reader,
    tenant: str | None = None,
    project: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = control_plane.DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Recorded sessions, newest first, optionally narrowed to one tenant or project.

    → `[{"id": str, "tenant": str, "project": str, "channel": "voice"|"chat",
         "started_at": float, "ended_at": float|null, "outcome": str|null,
         "events": int, "turns": int, "cost_eur": float|null}]`

    `cost_eur` and `outcome` are null while the call is still running.
    """
    return control_plane.sessions(store, tenant=tenant, project=project, limit=limit)


@app.get("/sessions/{session_id}")
async def session(session_id: str, store: Reader) -> dict[str, Any]:
    """One session: the list line, the end-of-call report, and every event in seq order.

    → `{...the /sessions line..., "report": object|null,
         "events": [{"seq": int, "t_ms": int, "kind": str, "payload": object}]}`

    `kind` is the log's own vocabulary (`session.start`, `stt.final`,
    `turn.user`, `turn.agent`, `state`, `tool.call`, `tool.result`,
    `stage.enter`, `tts.word`, `session.end`); a turn's latencies live in
    `payload.metrics`.
    """
    view = control_plane.session(store, session_id)
    if view is None:
        raise HTTPException(404, f"no session {session_id!r}")
    return view


@app.get("/sessions/{session_id}/live")
async def session_live(session_id: str, store: Reader, after: int = 0) -> StreamingResponse:
    """Server-sent events for one session's log as it appends, from `?after=<seq>`.

    Frames (`event:` / `data:`):
    - `open` — the `/sessions` line, once, so a late client can label the screen
    - `append` — `{"seq", "t_ms", "kind", "payload"}`, one per new log line
    - `end` — `{"seq", "outcome"}` when `session.end` lands; the stream closes
    - `error` — `{"error"}` for an unknown session id, then closes

    A `: keepalive` comment goes out after ten idle seconds. Reconnect with the
    last `seq` you saw in `?after=` — the log is append-only, so nothing is lost.
    """
    return StreamingResponse(
        control_plane.live(store, session_id, after=after),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.get("/live-calls")
async def live_calls(store: Reader) -> list[dict[str, Any]]:
    """Calls happening RIGHT NOW: the SFU's rooms an agent is in, newest first.

    → `[{"room": str, "sid": str, "participants": int, "started_at": float,
         "agent": true, "identities": [str], "phone": str|null,
         "session_id": str|null, "tenant": str|null, "project": str|null}]`

    An inbound phone call never passed through `/token`, so this is the only
    place it shows up before its log is worth reading. `session_id` is a best
    effort match against the sessions still running — by room name for a web
    call, by the caller's number for a phone one — and is null when neither
    answers; the room is still watchable with `POST /observe`.

    → 503 when the LiveKit server cannot be asked. "The SFU is down" and
    "nobody is calling" are different sentences and the console must not
    confuse them.
    """
    try:
        live = await rooms.active_rooms()
    except RoomsUnreachable as error:
        raise HTTPException(503, str(error)) from error
    return control_plane.live_calls(store, live)


@app.post("/observe")
def observe(req: ObserveRequest) -> dict[str, str]:
    """Mint a listen-only ticket into one live room, for a supervisor watching a call.

    → `{"url": str, "room": str, "identity": "observer:<hex>", "token": "<jwt>"}`

    The grant is `room_join` on that exact room with `can_publish=False`,
    `can_publish_data=False` and `hidden=True`: the browser receives audio and
    the agent's `lk.transcription` stream, publishes nothing, and never
    appears in the room — the caller is not told anybody joined.
    """
    return mint_observer(req.room)


@app.get("/pipeline/{tenant}/{project}")
async def pipeline_view(tenant: str, project: str, store: Reader) -> dict[str, Any]:
    """The three providers as data, plus what the console changed and what calls measured.

    → `{"tenant", "project", "name", "language", "greeting",
        "stt": {"provider", "model", "language_hints", "sample_rate",
                "endpointing": {"max_endpoint_delay_ms", "latency_adjustment_level",
                                "sensitivity"}, "keyterms"},
        "llm": {"provider", "model", "caching", "max_tokens",
                "cache_minimum_tokens", "cache_note"},
        "tts": {"provider", "model", "requested_model", "default_model", "latency_model",
                "forbidden_models", "forbidden_reasons", "voice", "sync_alignment"},
        "overrides": [{"field", "value", "updated_at"}], "overridable": [str],
        "latency": {"sessions": int, "turns": int,
                    "medians": {"transcription_delay", "end_of_turn_delay", "llm_node_ttft",
                                "tts_node_ttfb", "e2e_latency"}}}`

    Every value is what the NEXT session will use: the overrides are already
    applied to `greeting`, `tts.model` and `tts.voice`. A median is null when
    no stored voice session measured it.
    """
    known, effective = _effective(tenant, project, store)
    return pipeline.snapshot(known, effective, store)


@app.put("/pipeline/{tenant}/{project}")
async def pipeline_set(
    tenant: str, project: str, update: PipelineUpdate, store: Reader
) -> dict[str, Any]:
    """Change voice, TTS model or greeting for the next session — no deploy, no restart.

    Returns the same object as `GET /pipeline/{tenant}/{project}`, already
    reflecting the change, so the console renders one response instead of
    refetching. A model the platform refuses to run (`eleven_v3`,
    `eleven_turbo_v2_5`) is a 422 naming the rule; an unknown field is a 422
    from the body itself; a body that sets nothing is a 422 too.
    """
    edits = update.model_dump(exclude_none=True)
    if not edits:
        raise HTTPException(422, f"set at least one of {list(overrides.OVERRIDABLE)}")
    known, _ = _effective(tenant, project, store)
    for name, value in edits.items():
        refusal = pipeline.overridable(name, value)
        if refusal:
            raise HTTPException(422, refusal)
    for name, value in edits.items():
        store.set_pipeline_override(PipelineOverride(tenant, project, name, value))
    _, effective = _effective(tenant, project, store)
    return pipeline.snapshot(known, effective, store)


def _effective(tenant: str, project: str, store: Store) -> tuple[Tenant, Project]:
    """The registry's tenant and its project with the stored overrides already applied.

    The same `core.state.overrides.apply` the router runs, so the console can
    never show a pipeline different from the one the next call will use.
    """
    known = load_registry().get(tenant)
    if known is None:
        raise HTTPException(404, f"unknown tenant {tenant!r}; known: {sorted(load_registry())}")
    found = known.projects.get(project)
    if found is None:
        detail = f"tenant {tenant!r} has no project {project!r}; known: {sorted(known.projects)}"
        raise HTTPException(404, detail)
    return known, overrides.apply(tenant, found, store)


# Last, always: the SPA catch-all must not shadow an endpoint declared above it.
UI_IS_BUILT = mount_ui(app)
