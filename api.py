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

import time
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from core import control_plane, pipeline, rooms
from core.auth import mint_observer, mint_session
from core.context import Project, Tenant
from core.contracts import Channel, SessionMeta
from core.evals import runner as runner_module
from core.evals import runs as eval_runs_view
from core.evals import suites as eval_suites
from core.evals.runner import EvalRunBusy, EvalRunner
from core.registry import load_registry
from core.rooms import RoomsUnreachable
from core.state import overrides
from core.state.store import EvalRun, MetricScore, PipelineOverride, SQLiteStore, Store
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
    """The fields the console may change between calls; anything else is refused.

    `extra="forbid"`: a typo like `ttsModel` must come back as a 422 naming the
    field, not be stored as an override nothing will ever read.
    """

    model_config = ConfigDict(extra="forbid")

    voice: str | None = None
    tts_model: str | None = None
    greeting: str | None = None
    stt_provider: str | None = None
    llm_model: str | None = None


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
         "events": int, "turns": int, "cost_eur": float|null,
         "phone": str|null}]`

    `cost_eur` and `outcome` are null while the call is still running.

    `phone` is the caller's `sip.phoneNumber` (or the trunk's, when the caller
    withheld it) read off `session.start`, and null when the session never came
    in over the telephone. `channel` cannot say this: a phone call and a browser
    call are both `"voice"`, so this is the only field that separates them in
    the call log.
    """
    return control_plane.sessions(store, tenant=tenant, project=project, limit=limit)


@app.get("/sessions/{session_id}")
async def session(session_id: str, store: Reader) -> dict[str, Any]:
    """One session: the list line, the end-of-call report, and every event in seq order.

    → `{...the /sessions line (`phone` included), "report": object|null,
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
        "stt": {"provider", "requested_provider", "providers", "model", "language_hints",
                "sample_rate", "endpointing": "<the CHOSEN provider's own knobs>", "keyterms"},
        "llm": {"provider", "model", "requested_model", "default_model", "allowed_models",
                "caching", "max_tokens", "cache_minimum_tokens", "cache_note"},
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
    """Change an overridable pipeline field for the next session — no deploy, no restart.

    Returns the same object as `GET /pipeline/{tenant}/{project}`, already
    reflecting the change, so the console renders one response instead of
    refetching. A TTS model the platform refuses to run (`eleven_v3`,
    `eleven_turbo_v2_5`) is a 422 naming the rule, an `llm_model` outside the
    allow-list is a 422 naming the list, and an STT provider that is not
    `soniox` or `deepgram` is a 422 too; an unknown field is a 422 from the
    body itself; a body that sets nothing is a 422 too. An empty `voice` is a
    422 as well: nothing downstream refuses it — `tts_for` absorbs it as "no
    voice configured" and the next call is mute — so the rule lives here.
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


# ── evals ────────────────────────────────────────────────────────────────────
# The console's evals screen, whole: what a project can run, what every run
# scored, and the one subprocess this box will spend money on at a time.

# One runner per process, because "one run at a time" is a property of the BOX,
# not of a request. It opens its own store: it outlives the request that
# started it and a per-request connection would be closed under it.
EVAL_RUNNER = EvalRunner(SQLiteStore)


def evals_runner() -> EvalRunner:
    """This box's single eval slot, injected so a test can hand in a runner with a fake launcher."""
    return EVAL_RUNNER


Runner = Annotated[EvalRunner, Depends(evals_runner)]


class MetricScoreIn(BaseModel):
    """One metric's verdict over a whole run, as whoever ran it reports it."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    score: float
    passed: int = 0
    failed: int = 0


class EvalRunIn(BaseModel):
    """A finished run filing itself: which suite, which commit, what each metric scored."""

    model_config = ConfigDict(extra="forbid")

    tenant: str
    project: str
    suite: str
    status: str = "done"
    metrics: list[MetricScoreIn] = []
    git_sha: str | None = None
    milestone: str | None = None
    report_html: str | None = None
    detail: str | None = None


class EvalRunRequest(BaseModel):
    """What the console must name before this box spends minutes of paid LLM traffic."""

    model_config = ConfigDict(extra="forbid")

    tenant: str
    project: str
    suite: str


@app.get("/evals/suites")
def eval_suites_declared() -> list[dict[str, Any]]:
    """Every routable project and the eval suites it declares, for the console's Run buttons.

    → `[{"tenant": str, "project": str, "name": str, "suites": [str]}]`

    A suite id is a project's own data (`evals/suites.json`), never a name this
    process knows: ring 1 today, personas tomorrow, and nothing here changes.
    """
    return [
        {
            "tenant": tenant.id,
            "project": project.id,
            "name": project.name,
            "suites": sorted(eval_suites.declared(tenant.id, project.id)),
        }
        for tenant in load_registry().values()
        for project in tenant.projects.values()
    ]


@app.get("/evals/runs")
async def eval_runs(
    store: Reader,
    tenant: str | None = None,
    project: str | None = None,
    suite: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = eval_runs_view.DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Stored eval runs, newest first, each diffed against the previous run of the same suite.

    → `[{"id", "tenant", "project", "suite", "status": "running"|"done"|"failed",
         "started_at": float, "finished_at": float|null, "git_sha": str|null,
         "milestone": str|null, "report_html": str|null, "log_path": str|null,
         "detail": str|null, "previous": str|null,
         "metrics": [{"metric", "score", "passed", "failed", "delta": float|null}]}]`

    `delta` is this metric's score minus what the previous scored run of the
    same tenant/project/suite gave it, and null when there was no previous one.
    """
    return eval_runs_view.listing(store, tenant=tenant, project=project, suite=suite, limit=limit)


@app.post("/evals/runs")
async def file_eval_run(body: EvalRunIn, store: Reader) -> dict[str, Any]:
    """Register a run that finished somewhere else — a laptop, CI, `core.testing.report`.

    Returns the same object one line of `GET /evals/runs` holds, diff included,
    so the caller sees at once whether it improved on the last one.
    """
    run = EvalRun(
        id=runner_module.run_stamp(),
        tenant=body.tenant,
        project=body.project,
        suite=body.suite,
        status=body.status,
        started_at=time.time(),
        finished_at=time.time(),
        git_sha=body.git_sha,
        milestone=body.milestone,
        metrics=tuple(MetricScore(**m.model_dump()) for m in body.metrics),
        report_html=body.report_html,
        detail=body.detail,
    )
    store.add_eval_run(run)
    return eval_runs_view.view(run, eval_runs_view.previous(store.eval_runs(), run))


@app.post("/evals/run")
async def launch_eval_run(req: EvalRunRequest, store: Reader, runner: Runner) -> dict[str, Any]:
    """Run one project's suite on this box and answer at once with the run to poll.

    → the `GET /evals/runs` line, `status: "running"`.

    → 404 when that project declares no such suite (the message lists the ones
    it does), and 409 while another run is alive: this box runs ONE eval at a
    time and refuses a second rather than queueing a bill nobody is watching.
    """
    try:
        target = eval_suites.target(req.tenant, req.project, req.suite)
    except eval_suites.UnknownSuite as error:
        raise HTTPException(404, str(error)) from error
    try:
        run = await runner.start(req.tenant, req.project, req.suite, target)
    except EvalRunBusy as error:
        raise HTTPException(409, str(error)) from error
    return eval_runs_view.view(run)


@app.get("/evals/run/{run_id}")
async def eval_run(run_id: str, store: Reader, runner: Runner) -> dict[str, Any]:
    """One run's standing while it happens: `running`, `done` or `failed`, with its log tail.

    → the `GET /evals/runs` line plus `{"log": [str], "busy": bool}` — the last
    lines the subprocess wrote, and whether this box is still holding a slot.

    The log is the child's own output and nothing else; no environment and no
    provider key is ever written to it or read back out of it.
    """
    view = eval_runs_view.find(store, run_id)
    if view is None:
        raise HTTPException(404, f"no eval run {run_id!r}")
    stored = next(row for row in store.eval_runs() if row.id == run_id)
    return {**view, "log": runner.tail(stored), "busy": runner.busy}


# Last, always: the SPA catch-all must not shadow an endpoint declared above it.
UI_IS_BUILT = mount_ui(app)
