"""score_session: read a finished call back out of the store, judge it, append the verdict.

The whole of ring 4 in one function, and every refusal it can make is a
sentence a caller can print:

    not found · still running · already scored · scoring is off for this project

None of them is an error. A session scored twice would be the error, and the
store is what prevents it: `session.score` takes the next `seq`, and `events`
has `(session_id, seq)` as its primary key with append-only triggers over it,
so two scorers racing the same call end with one row and one loser — no lock,
no flag column, no window.

Why the imports are inside the function: `core.testing.replay` and the judge
pull `deepeval` in, which costs a second and opens a telemetry client. `api.py`
imports this module at startup and must pay neither until a call is actually
scored.
"""

import logging
from typing import Any

from core.registry import load_registry
from core.scoring import report as scoring_report
from core.scoring.report import ScoreReport
from core.scoring.rules import rules_for
from core.state.events import Event
from core.state.store import SQLiteStore, Store

log = logging.getLogger("platform.scoring")

NOT_FOUND = "no session {id!r} in this store"
STILL_RUNNING = "the call is still going: nothing to score yet"
SCORING_OFF = "{tenant}/{project} has scoring switched off"
UNROUTABLE = "{tenant}/{project} is not routable on this deploy"
RACED = "another scorer got there first"


def score_session(
    session_id: str,
    store: Store | None = None,
    judge: bool = True,
) -> dict[str, Any]:
    """Score one finished session and write `session.score`; idempotent, never raises.

    → `{"session": id, "scored": bool, "score": <payload>|None, "skipped": str|None}`

    `store` is opened here when the caller gives none, because this runs in a
    worker thread and a SQLite connection belongs to the thread that made it.
    `judge=False` runs the free half alone — what a test, or a deploy with no
    key, gets for nothing.
    """
    store = store or SQLiteStore()
    row = store.session(session_id)
    if row is None:
        return _refused(session_id, NOT_FOUND.format(id=session_id))
    events = store.events(session_id)
    scored = scoring_report.already_scored(events)
    if scored is not None:
        return {"session": session_id, "scored": False, "score": scored, "skipped": None}
    if not scoring_report.finished(row, events):
        return _refused(session_id, STILL_RUNNING)
    off = _disabled(row.tenant, row.project)
    if off:
        return _refused(session_id, off)

    built = build_report(row.tenant, row.project, events, row.outcome or "", judge=judge)
    payload = built.payload()
    event = Event(
        seq=scoring_report.next_seq(events),
        kind=scoring_report.SCORE_KIND,
        t_ms=_at_end(events),
        payload=payload,
    )
    try:
        store.append(session_id, event)
    except Exception:  # noqa: BLE001 — a taken seq means somebody else scored it; that is fine
        log.info("%s was scored by another writer while we judged it", session_id)
        return _refused(session_id, RACED)
    log.info("scored %s: %s %s", session_id, payload["score"], payload["verdict"])
    return {"session": session_id, "scored": True, "score": payload, "skipped": None}


def build_report(
    tenant: str,
    project: str,
    events: list[Event],
    outcome: str,
    judge: bool = True,
) -> ScoreReport:
    """Every check this call earns, deterministic first, the one judged metric last.

    Split out of `score_session` because it touches neither the store nor the
    clock: hand it a list of events and it hands back a verdict, which is how
    the checks are tested without a database and without a euro.
    """
    # deepeval lands here and nowhere earlier — see the module docstring.
    from core.scoring import checks as deterministic_checks
    from core.scoring import judge as judge_module
    from core.testing import replay

    rules = rules_for(tenant, project)
    turns = replay.turns_from(events)
    report = ScoreReport(
        checks=deterministic_checks.deterministic(events, turns, rules, outcome),
        turns=len(turns),
    )
    if not judge:
        return report
    if not turns:
        # A caller who hung up before a word was said. The free checks above still
        # stand; the judge's case CANNOT be built (DeepEval refuses empty turns),
        # and before this guard the sweeper retried that TypeError forever — one
        # silent call wedging the whole queue behind it. Found live on the box.
        return report
    case = _case(turns, tenant, project)
    check, run = judge_module.judge(case, rules)
    return ScoreReport(
        checks=[*report.checks, *([check] if check else [])],
        judge=run,
        turns=report.turns,
    )


def _case(turns: list, tenant: str, project: str):
    """The replayed turns as the conversational case the judge reads."""
    from deepeval.test_case import ConversationalTestCase

    return ConversationalTestCase(
        turns=turns,
        name=f"{tenant}/{project}",
        scenario=replay_scenario(tenant, project),
    )


def replay_scenario(tenant: str, project: str) -> str:
    """One line telling the judge what it is reading: a real call, not a golden."""
    return f"A real call of {tenant}/{project}, replayed from its append-only log."


def _disabled(tenant: str, project: str) -> str | None:
    """The sentence to refuse with when this project opted out, or None when it is scored.

    A tenant the registry cannot import is unroutable, not opted out, and the
    two are reported differently: one is a decision somebody made, the other is
    a deploy that is broken and should read as broken.
    """
    known = load_registry().get(tenant)
    found = known.projects.get(project) if known else None
    if found is None:
        return UNROUTABLE.format(tenant=tenant, project=project)
    if not getattr(found, "scoring", True):
        return SCORING_OFF.format(tenant=tenant, project=project)
    return None


def _at_end(events: list[Event]) -> int:
    """The score's offset in log time: where the call ended, not where the scorer ran."""
    return max((event.t_ms for event in events), default=0)


def _refused(session_id: str, why: str) -> dict[str, Any]:
    return {"session": session_id, "scored": False, "score": None, "skipped": why}
