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

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from core import business, control_plane, pipeline, recordings, rooms
from core import outcomes as core_outcomes
from core.auth import (
    SupervisorCapability,
    mint_caller,
    mint_observer,
    mint_session,
    mint_supervisor,
)
from core.context import Project, Tenant
from core.contracts import Channel, SessionMeta
from core.evals import goldens as eval_goldens_view
from core.evals import runner as runner_module
from core.evals import runs as eval_runs_view
from core.evals import suites as eval_suites
from core.evals.runner import EvalRunBusy, EvalRunner
from core.registry import load_registry
from core.rooms import RoomsUnreachable
from core.scoring import sweeper
from core.scoring.runner import score_session
from core.security import desk
from core.state import overrides
from core.state.store import EvalRun, MetricScore, PipelineOverride, SQLiteStore, Store
from core.telephony import lines as phone_lines
from core.webui import mount_ui

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Seed the phone routes this deploy owns, then run the post-call scorer beside the API.

    The seed runs once, at startup, and only writes a number the store does not
    already carry (`core.telephony.lines.seed`): the control plane owns the
    number → project table, so a fresh database must not answer "no line" for a
    number that has been ringing for weeks.

    The sweeper is a task of this process and not a cron entry because it must
    stop when the control plane stops: a sweeper still judging calls against a
    database whose owner has gone is spending money nobody is watching.
    `SCORING_SWEEP=0` starts nothing at all.
    """
    phone_lines.seed(SQLiteStore())
    if not sweeper.enabled():
        yield
        return
    task = asyncio.create_task(sweeper.run())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="convo control plane", lifespan=lifespan)


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


class SuperviseRequest(BaseModel):
    """A supervisor asking to be let into one live room, with one set of powers."""

    model_config = ConfigDict(extra="forbid")

    room: str
    capability: SupervisorCapability = "listen"
    user_id: str = ""


class EnteredRequest(BaseModel):
    """A supervisor saying they are through the door; the SFU is asked whether it is true.

    Nothing here is trusted beyond "look at this room for this identity". The
    capability is read off the participant's signed attributes at the SFU, not
    taken from this body — which is why there is no field for it.
    """

    model_config = ConfigDict(extra="forbid")

    room: str
    identity: str


class VerbRequest(BaseModel):
    """One supervision verb, aimed at a live room from the control plane rather than a browser.

    `identity` is the supervisor the SFU will be asked about; nothing here is
    trusted beyond "look at this room for this identity". The agent asks the
    same question again of the packet it receives.

    `mode` is per-verb and deliberately one field: `inject` / `inject_and_speak`
    for a steer, `cold` / `warm` for a transfer. Empty means "this verb's
    default", which is the only value that is right for every verb.
    """

    model_config = ConfigDict(extra="forbid")

    room: str
    identity: str
    verb: Literal["steer", "takeover", "release", "transfer"]
    text: str = ""
    mode: Literal["", "inject", "inject_and_speak", "cold", "warm"] = ""
    deaf: bool = False
    to: str = ""


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
    # E.164, or "" to take the handover verb away from the agent entirely.
    transfer_number: str | None = None


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
         "phone": str|null, "score": object|null, "audio": bool}]`

    `cost_eur` and `outcome` are null while the call is still running.

    `score` is the payload of this session's `session.score` event, or null —
    which means one of three different things and the console must not read it
    as "bad": the call has not been scored yet, it was too short, or its
    project has scoring switched off. Its shape is
    `{"version", "score": 0-1, "verdict": "pass"|"fail", "failed": [str],
      "turns": int, "checks": [{"name", "kind", "passed", "score"?, "reason"}],
      "judge": {"ran", "skipped", "model", "threshold", "cap_eur", "cost_eur"}}`.

    `phone` is the caller's `sip.phoneNumber` (or the trunk's, when the caller
    withheld it) read off `session.start`, and null when the session never came
    in over the telephone. `channel` cannot say this: a phone call and a browser
    call are both `"voice"`, so this is the only field that separates them in
    the call log.

    `audio` is whether `GET /sessions/{id}/recording` will answer with an OGG:
    a look on disk, so a chat, a project that opted out of recording and a job
    killed before its first flush all read false and the console draws no
    player rather than a broken one.
    """
    return control_plane.sessions(store, tenant=tenant, project=project, limit=limit)


@app.get("/outcomes")
async def outcomes(
    store: Reader,
    tenant: str | None = None,
    project: str | None = None,
    days: Annotated[int, Query(ge=1, le=core_outcomes.MAX_DAYS)] = core_outcomes.DEFAULT_DAYS,
    limit: Annotated[int, Query(ge=1, le=core_outcomes.MAX_ROWS)] = core_outcomes.DEFAULT_ROWS,
) -> dict[str, Any]:
    """What the platform DID to the business: irreversible transactions, counted off the log.

    → `{"tenant": str|null, "project": str|null, "days": int,
         "since": float, "until": float,
         "totals": {"transactions": int, "confirmed": int, "failed": int, "sessions": int},
         "verbs": [{"verb": str, "count": int, "confirmed": int, "failed": int, "pending": int}],
         "series": [{"day": "YYYY-MM-DD", "total": int, "verbs": {str: int}}],
         "rows": [{"session": str, "tenant": str, "project": str, "channel": str,
                   "seq": int, "at": float, "day": str, "verb": str,
                   "confirmed": bool, "status": "done"|"failed"|"pending",
                   "summary": str|null}]}`

    A transaction is one `tool.call` whose `side_effect` is `irreversible` —
    the verb is the tool's own name and nothing here knows which names exist,
    so a project that declares a new irreversible tool appears on this board
    the first time it runs. `confirmed` is whether a `confirm.granted` for that
    tool stood unspent before the call: the caller's yes, paired one to one.

    `summary` is the line the tool's own `result_summary` rendered and the
    session's PII mask scrubbed, reused verbatim; it is null for a tool that
    declares no renderer and for one that failed. Nothing is re-rendered here.

    `series` covers every day of the window, empty days included, so a bar
    strip has a stable axis; `rows` is newest first and capped by `limit`.
    There is no rollup table — see `core/outcomes.py` for why.
    """
    return core_outcomes.outcomes(
        store, tenant=tenant, project=project, days=days, limit=limit
    )


@app.get("/reservations")
async def reservations(
    store: Reader,
    tenant: str,
    project: str,
    days: Annotated[int, Query(ge=1, le=business.MAX_DAYS)] = business.DEFAULT_DAYS,
    limit: Annotated[int, Query(ge=1, le=business.MAX_ROWS)] = business.DEFAULT_ROWS,
) -> dict[str, Any]:
    """The reservations THEMSELVES, read off the customer's own system — not off our log.

    → `{"tenant": str, "project": str, "days": int, "shape": str|null,
         "labels": {str: str|null}, "systems": [str],
         "rows": [{"id": str, "who": str, "contact": str|null, "when": str|null,
                   "handled_by": str|null, "state": str,
                   "tone": "new"|"changed"|"gone"|"plain",
                   "detail": str|null, "at": float|null, "session": str|null,
                   "verb": str|null, "confirmed": bool, "channel": str|null}],
         "views": [{"shape": …, "labels": …, "systems": …, "rows": […]}]}`

    `views` is one entry per system of this tenant that offers a record view,
    in the order the tenant's own factory builds them, and the flat `shape`,
    `labels`, `systems` and `rows` are the first of them. A shop that keeps its
    orders in one system and its incidents in another answers with two, each
    with its own shape and its own words for a state — they are two tables and
    not a longer one, and deciding which of a business's vocabularies wins is
    not the platform's to do.

    `/outcomes` counts what the platform DID, off the append-only log whose
    summaries are PII-filtered by design. This is the other reading and the one
    an operator asked for: who is coming, when, with whom, and whether that
    booking still stands. A patient's name is not in our log and must not be —
    it is in the clinic's booking system, which is where this goes to get it
    (`core.registry` → the tenant's adapters → `list_records`).

    `shape` is the business's own word for its records (`appointments`,
    `orders`) and `labels` its own column headings: a project whose systems
    offer no such view answers `shape: null` with no rows, and the console says
    so rather than drawing an agenda nobody has. Nothing in `core` or in the UI
    holds a list of shapes, columns or state words.

    `state` is the business's word for how a record stands and `tone` the only
    presentational field, decided by the adapter that knows what its own words
    mean. `session`, `verb` and `confirmed` are the join with `/outcomes`: the
    call that last touched this record inside the window, matched on the
    identifier the log's summary carries verbatim. Null means no call in the
    window touched it — see `core/business.py` for why that join is on an id
    and not on a name.
    """
    known = load_registry().get(tenant)
    if known is None:
        raise HTTPException(404, f"unknown tenant {tenant!r}; known: {sorted(load_registry())}")
    if project not in known.projects:
        detail = f"tenant {tenant!r} has no project {project!r}; known: {sorted(known.projects)}"
        raise HTTPException(404, detail)
    return await business.records(known, project, store, days=days, limit=limit)


@app.get("/sessions/{session_id}")
async def session(session_id: str, store: Reader) -> dict[str, Any]:
    """One session: the list line, the end-of-call report, and every event in seq order.

    → `{...the /sessions line (`phone` and `audio` included), "report": object|null,
         "events": [{"seq": int, "t_ms": int, "kind": str, "payload": object}]}`

    `kind` is the log's own vocabulary (`session.start`, `stt.final`,
    `turn.user`, `turn.agent`, `state`, `tool.call`, `tool.result`,
    `stage.enter`, `tts.word`, `session.end`, `session.score`); a turn's
    latencies live in `payload.metrics`, and the score's breakdown in the
    `session.score` payload — which is also lifted onto the `score` field of
    the list line above, so a screen never has to walk the log to draw a chip.
    """
    view = control_plane.session(store, session_id)
    if view is None:
        raise HTTPException(404, f"no session {session_id!r}")
    return view


@app.post("/sessions/{session_id}/score")
async def score(session_id: str) -> dict[str, Any]:
    """Score one finished session now, and write the verdict into its log. Idempotent.

    → `{"session": str, "scored": bool, "score": object|null, "skipped": str|null}`

    `scored` is true only when THIS call wrote the event. A session that was
    already scored comes back with `scored: false` and the score it already
    has; one that cannot be scored yet comes back with `skipped` saying why in
    a sentence ("the call is still going", "clinica-norte/x has scoring
    switched off"). None of those is an error and none of them is a 4xx: asking
    twice is the normal way to use this door, and the sweeper asks constantly.

    The work runs in a worker thread, with its own store opened inside it: the
    judge is a blocking HTTP call and a SQLite connection belongs to the thread
    that created it. The store is therefore NOT the injected `Reader` — this is
    the one route in the file that opens its own.
    """
    return await asyncio.to_thread(score_session, session_id)


@app.get("/sessions/{session_id}/recording")
async def session_recording(
    session_id: str,
    store: Reader,
    t: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> FileResponse:
    """The stereo OGG of one call: the caller on the left channel, the agent on the right.

    → `audio/ogg`, `Content-Disposition: inline; filename="<session_id>.ogg"`

    Recordings hold PII, so this is the ONLY way one leaves the box: they live
    outside git under `CONVO_RECORDINGS`, are never mounted as static files,
    and are looked up by SESSION ID — the path is composed here from a
    validated id, never read out of a log payload a job wrote.

    → 404 for a session this deploy has never heard of, and 404 for a session
    with no audio (a chat, a project that opted out, a job killed before its
    first flush). Both are "there is nothing to play"; telling them apart
    would be telling a stranger which session ids exist.

    → 401 when the deploy sets `RECORDINGS_TOKEN` and the request does not
    present it, as `Authorization: Bearer <token>` or `?t=<token>` — the query
    form exists because an `<audio src>` cannot send a header. With no such
    variable set the route is exactly as open as every other read on this API,
    and `infra/box/README.md` says so out loud.
    """
    presented = t or (authorization or "").removeprefix("Bearer ").strip() or None
    if not recordings.authorised(presented):
        raise HTTPException(401, "this deploy requires a recordings token")
    if store.session(session_id) is None:
        raise HTTPException(404, f"no session {session_id!r}")
    path = recordings.for_session(session_id)
    if path is None:
        raise HTTPException(404, f"session {session_id!r} kept no audio")
    return FileResponse(
        path,
        media_type=recordings.MEDIA_TYPE,
        headers={"Content-Disposition": f'inline; filename="{session_id}.ogg"'},
    )


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


class EvalRoomRequest(BaseModel):
    """What a ring-2 harness must name to get a room the fleet already answers in."""

    model_config = ConfigDict(extra="forbid")

    tenant: str
    project: str
    persona: str | None = None
    identity: str = "deepeval-caller"


@app.post("/evals/rooms")
async def eval_room(req: EvalRoomRequest, store: Reader) -> dict[str, str]:
    """Mint a room for a synthetic caller: the agent is dispatched before anybody joins.

    → `{"url": str, "room": "eval-<tenant>-<project>-<hex>", "identity": str,
        "token": "<jwt>"}`

    The eval twin of `POST /token`, and it exists because of one verified
    limitation: DeepEval's `LiveKitConnector` signs its own join token and can
    dispatch only by `agent_name`, never with metadata — so a room it opens by
    itself reaches a worker that cannot tell which tenant is calling. Here the
    dispatch is made server-side with the same `SessionMeta` JSON `/token`
    puts inside the JWT, and the ticket returned carries no dispatch of its
    own: the room already has one, and two would seat two agents.

    Refused with 404 for a tenant or project this deployment cannot route, and
    with 503 when the LiveKit server cannot be reached — a harness must not
    read "the SFU is down" as "the agent never answered".
    """
    _effective(req.tenant, req.project, store)  # 404s unless the fleet can route it
    meta = SessionMeta(tenant=req.tenant, project=req.project, channel="voice")
    try:
        room = await rooms.create_eval_room(meta, persona=req.persona)
    except RoomsUnreachable as error:
        raise HTTPException(503, str(error)) from error
    return mint_caller(room, tenant=req.tenant, identity=req.identity)


@app.post("/supervise")
def supervise(req: SuperviseRequest) -> dict[str, str]:
    """Mint a role-scoped, short-lived ticket for a supervisor entering one live call.

    → `{"url": str, "room": str, "identity": "sup:<uid>", "capability": str,
         "token": "<jwt>"}`

    `capability` is the whole of the difference: `listen` is hidden and
    subscribe-only, `whisper` may also send data, `takeover` publishes audio
    and appears in the room. The ticket expires in
    `core.auth.SUPERVISOR_TTL`, so it is a ticket to this call and not a
    standing key to the room.

    This is where a deployment's own auth goes: the handler is deliberately
    thin, and the human on the other side of it is authenticated by whatever
    the control plane already authenticates humans with. Everything downstream
    — the SFU and the agent both — trusts only the signed `sup:` identity in
    the JWT this returns, never a role a client claims in a payload.
    """
    return mint_supervisor(req.room, req.capability, user_id=req.user_id)


@app.post("/supervise/entered")
async def supervise_entered(req: EnteredRequest) -> dict[str, Any]:
    """Record that a supervisor really did enter this call, and say what the SFU sees.

    → `{"identity": "sup:<uid>", "capability": str, "hidden": bool, "announced": bool}`

    Two things happen and both matter. The SFU is asked who is in the room, so
    the answer is a *presence* and not a ticket somebody was handed — `hidden`
    is the server's own word for "the caller cannot see this participant", which
    is what the desk shows the supervisor. And the arrival is announced to the
    room's agent alone, on the `supervisor` data topic, which is what puts
    `supervisor.join` in the caller's log with the next `seq`: the job process
    owns that log, so the fact has to reach it rather than be written around it.

    `announced` is False when no agent is in the room — nothing is being logged
    there either. → 404 when the identity is not in the room, 503 when the SFU
    cannot be asked.
    """
    try:
        return await desk.entered(req.room, req.identity)
    except desk.NotInRoom as error:
        raise HTTPException(404, str(error)) from error
    except RoomsUnreachable as error:
        raise HTTPException(503, str(error)) from error


@app.post("/supervise/verb")
async def supervise_verb(req: VerbRequest) -> dict[str, Any]:
    """Whisper to a live agent, take its line, hand it back, or move the call — server-side.

    → `{"verb": str, "identity": "sup:<uid>", "sent": true}`

    The browser desk does not come through here: it holds a `whisper` ticket
    and calls the agent's own `supervisor.steer` RPC, which is one hop instead
    of three. This exists for the callers that have no room connection — an
    escalation rule, a compliance trigger, a `curl` in a terminal — and for
    the demo that shows a whisper landing without a browser at all:

        curl -XPOST localhost:8000/supervise/verb -H 'content-type: application/json' \
          -d '{"room":"...","identity":"sup:berna","verb":"steer","text":"ve al grano"}'

    A transfer is the same door with a destination on it — `mode` is `cold`
    (a SIP REFER: the caller leaves for that number and the call ends here) or
    `warm` (the colleague is dialled INTO the room, briefed where the caller
    cannot hear it, then bridged), and `to` is E.164, defaulting to the
    deployment's `TRANSFER_TO`:

        curl -XPOST localhost:8000/supervise/verb -H 'content-type: application/json' \
          -d '{"room":"...","identity":"sup:berna","verb":"transfer","mode":"cold",
               "to":"+34600111222"}'

    What happens next is the agent's decision, not this handler's: the packet
    reaches the job that owns the caller's log, `SupervisorControl` checks the
    identity again, applies the verb at a turn boundary and writes the line
    with the next `seq`. → 404 when the supervisor or the agent is not in the
    room, 422 for a verb this door does not forward, 503 when the SFU cannot
    be asked.
    """
    body = {"text": req.text, "mode": req.mode, "deaf": req.deaf, "to": req.to}
    try:
        return await desk.command(req.room, req.identity, req.verb, body)
    except desk.NotInRoom as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RoomsUnreachable as error:
        raise HTTPException(503, str(error)) from error


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


@app.get("/evals/goldens/{tenant}/{project}")
def eval_goldens(tenant: str, project: str) -> dict[str, Any]:
    """What each of a project's suites actually asks of the agent, so it is readable on screen.

    → `{"tenant", "project", "suites": [{"suite", "target", "dataset",
         "kind": "turn"|"call"|"code", "count": int|null, "goldens": [...]}]}`

    A `turn` golden is `{"input", "turn", "expected_behaviour", "expected_tools"}`
    — one line of a caller and what must come back. A `call` golden is
    `{"name", "persona", "objective", "turns", "policies", "max_turns"}` — a
    whole conversation and the hard policies that must survive it. A `code`
    suite writes its cases in python instead of JSON: `count` is null and
    `target` says where to read them.

    `suite` is the same id a run carries, so the console can put a suite's
    goldens next to its runs. Read-only on purpose: goldens are edited in git,
    where a reviewer sees the change.

    → 404 when nothing on disk answers to that tenant and project. The files are
    READ, never imported: no tenant module enters this process because somebody
    asked what a project evaluates.
    """
    try:
        return eval_goldens_view.datasets(tenant, project)
    except eval_goldens_view.UnknownProject as error:
        raise HTTPException(404, str(error)) from error


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
