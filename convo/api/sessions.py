"""Recorded and live sessions: the list, one session, its score, its audio, its live log."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from convo.api import client as control_plane
from convo.api.deps import SSE_HEADERS, Reader
from convo.scoring.runner import score_session
from convo.session import recordings, rooms
from convo.session.rooms import RoomsUnreachable

router = APIRouter()


@router.get("/sessions")
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


@router.get("/sessions/{session_id}")
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


@router.post("/sessions/{session_id}/score")
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


@router.get("/sessions/{session_id}/recording")
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


@router.get("/sessions/{session_id}/live")
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


@router.get("/live-calls")
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
