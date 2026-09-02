"""The console's evals screen: rooms for a synthetic caller, suites, goldens, runs."""

import time
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from convo.api.auth import (
    mint_caller,
)
from convo.api.deps import Reader, Runner, effective
from convo.domain.contracts import SessionMeta
from convo.evals import goldens as eval_goldens_view
from convo.evals import runner as runner_module
from convo.evals import runs as eval_runs_view
from convo.evals import suites as eval_suites
from convo.evals.runner import EvalRunBusy
from convo.session import rooms
from convo.session.registry import load_registry
from convo.session.rooms import RoomsUnreachable
from convo.state.store import EvalRun, MetricScore

router = APIRouter()


class EvalRoomRequest(BaseModel):
    """What a ring-2 harness must name to get a room the fleet already answers in."""

    model_config = ConfigDict(extra="forbid")

    tenant: str
    project: str
    persona: str | None = None
    identity: str = "deepeval-caller"


@router.post("/evals/rooms")
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
    effective(req.tenant, req.project, store)  # 404s unless the fleet can route it
    meta = SessionMeta(tenant=req.tenant, project=req.project, channel="voice")
    try:
        room = await rooms.create_eval_room(meta, persona=req.persona)
    except RoomsUnreachable as error:
        raise HTTPException(503, str(error)) from error
    return mint_caller(room, tenant=req.tenant, identity=req.identity)


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


@router.get("/evals/suites")
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


@router.get("/evals/goldens/{tenant}/{project}")
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


@router.get("/evals/runs")
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


@router.post("/evals/runs")
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


@router.post("/evals/run")
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


@router.get("/evals/run/{run_id}")
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
