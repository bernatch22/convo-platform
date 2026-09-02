"""Ring 3 on a ROUTED session: the call the dispatcher sent here, scored from its own log.

`test_stored_session_deepeval.py` records its own conversation and reads it
back out of a `MemoryStore`. This module runs no conversation at all: it opens
the store `worker.py dev` wrote and scores whichever session the LiveKit
dispatcher routed to it — the only case in the suite whose input travelled
through a real SFU, chosen by `RoomAgentDispatch` metadata rather than by a
test that knew the answer.

So it is skipped unless that call has happened. `scripts/dev_call.py` is what
makes it run; a suite failing here because nobody started a server would be
reporting on the laptop, not on the code:

    docker compose -f infra/compose/dev.yml up -d
    uv run uvicorn api:app --port 8090
    uv run python worker.py dev            # no TENANT, no PROJECT in its env
    uv run python scripts/dev_call.py
    uv run deepeval test run tests/evals/test_dispatch_ring.py

What it asserts is the consent policy, for the reason ring 3 always gives:
`grounded_facts_dag` cannot ground a claim whose evidence the log deliberately
does not keep (`core/testing/replay.py`, `docs/evals.md` §3.6). Its score is
printed with the calls it could not see, and never asserted.
"""

import pytest

from convo.state.store import SQLiteStore
from convo.state.store.protocol import SessionRow
from convo.testing import replay
from convo.testing.metrics.deepeval import project_metrics

pytestmark = pytest.mark.evals

ROUTED = [("clinica-norte", "reagendamiento"), ("tienda-sur", "pedidos")]
NO_CALL = "no routed chat session for {0}/{1} in this store — run scripts/dev_call.py first"


@pytest.mark.parametrize(("tenant", "project"), ROUTED)
def test_a_routed_session_is_logged_under_the_tenant_the_dispatcher_named(
    tenant: str, project: str
) -> None:
    """The worker had no TENANT in its environment, so the log can only name who dispatched it."""
    row = routed_session(tenant, project)
    events = SQLiteStore().events(row.id)

    opening = events[0]
    assert opening.kind == "session.start"
    assert (opening.payload["tenant"], opening.payload["project"]) == (tenant, project)
    channel = opening.payload["channel"]
    assert channel == "chat", "the channel belongs to the session, never to the project"
    assert [event for event in events if event.kind == "stage.enter"], "the project never opened"


@pytest.mark.parametrize(("tenant", "project"), ROUTED)
def test_a_routed_session_replays_into_a_case_the_consent_policy_passes(
    tenant: str, project: str
) -> None:
    """The project's own DAG, run on a call that really happened over WebRTC."""
    row = routed_session(tenant, project)
    case = replay.conversational_case_from(
        SQLiteStore(), row.id, replay.descriptions_for(tenant, project)
    )
    assert len(case.turns) >= 4, f"{row.id} is too short to score: {len(case.turns)} turns"

    metrics = project_metrics(tenant, project)
    consent = metrics.consent_policy()
    score = consent.measure(case)
    print(f"\n{row.id} {tenant}/{project} consent_policy: {score} — {consent.reason}")
    _print_grounding(metrics, case, row)

    assert score >= consent.threshold, consent.reason


def routed_session(tenant: str, project: str) -> SessionRow:
    """The newest chat session this project ran, or skip: the live run is this test's fixture."""
    rows = SQLiteStore().sessions()
    for row in rows:
        if (row.tenant, row.project, row.channel) == (tenant, project, "chat"):
            return row
    pytest.skip(NO_CALL.format(tenant, project))


def _print_grounding(metrics, case, row: SessionRow) -> None:
    """Report the grounding score next to what the log could not show it, and assert neither."""
    grounding = metrics.grounded_facts_dag()
    blind = replay.missing_tool_outputs(case)
    print(f"{row.id} grounded_facts_dag: {grounding.measure(case)} (not asserted)")
    print(f"  results the log kept as a shape, never a payload: {blind or 'none'}")
