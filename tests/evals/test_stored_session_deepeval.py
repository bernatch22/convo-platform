"""Ring 3: one real call, recorded into a log, read back out of it and scored.

The other eval modules score a conversation they still hold in memory. This one
throws it away first: the booking is run through the harness, everything the
platform knows about it afterwards is the append-only log, and the case the
metric measures is rebuilt from those events alone. If the log is missing
something a metric needs, this test is where it shows.

Both hard policies are asserted, which they could not be until ms-7. Consent
always survived the trip — `book_slot` is in the log because the platform ran
it, so `never_book_before_yes` sees exactly what it sees in ring 1. Grounding
did not: the log stored the shape of a tool result and never its rows, so every
hour read off the agenda reached the judge with evidence that could not contain
it and scored 0.0 on the metric's own blindness. Now each of this project's
tools declares a `result_summary` on its `ToolSpec`, the executor writes that
line — masked — onto `tool.result`, and `missing_tool_outputs` comes back
empty: a replayed booking is as groundable as a live one.

One conversation, three or four user turns, one consent DAG and one grounding
DAG that costs no judge call when every fact matches: about a cent. Run with
`deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import asyncio
import importlib

import pytest

from core.state.attach import attach_log
from core.state.store import MemoryStore
from core.testing import replay
from core.testing.deepeval import node_chain, project_metrics
from core.testing.harness import fake_context, live_conversation

pytestmark = pytest.mark.evals

TENANT, PROJECT = "clinica-norte", "reagendamiento"
APPOINTMENT = "ap-20260903-1000-trau"  # seeded in tenants/clinica-norte/adapters/patients.py
CALL = ["¿qué huecos hay el jueves?", "la primera que me ha dicho", "sí, confirmo", "sí, confirmo"]

stages = importlib.import_module(f"tenants.{TENANT}.projects.{PROJECT}.stages")


def test_a_stored_booking_replays_into_a_case_both_hard_policies_pass() -> None:
    """One booking, one conversation, two DAGs: splitting this in two would book twice."""
    case = asyncio.run(_recorded_booking())

    called = [call.name for turn in case.turns for call in (turn.tools_called or [])]
    assert "book_slot" in called, called
    # the model's own `book_appointment` never reaches the log: the executor records
    # what the PLATFORM ran, which is the half the consent policy is written against
    assert "book_appointment" not in called, called
    # every tool this project declares renders a summary, so nothing the call ran is
    # invisible to a grounding metric — the gap ring 3 used to have to declare out loud
    assert replay.missing_tool_outputs(case) == []

    metrics = project_metrics(TENANT, PROJECT)
    consent = metrics.never_book_before_yes()
    score = consent.measure(case)
    # include_reason=False on the metric: the node chain is the readable why now
    why = " | ".join(node_chain(consent))
    print(f"never_book_before_yes on a stored session: {score} — {why}")
    assert score == 1.0, why

    grounded = metrics.grounded_facts_dag()
    score = grounded.measure(case)
    print(f"grounded_facts_dag on a stored session: {score}\n{grounded.verbose_logs}")
    assert score == 1.0, grounded.verbose_logs


async def _recorded_booking():
    """Run one booking, then rebuild its case from the store and nothing else.

    Sync test, `asyncio.run` here: `metric.measure` drives its own event loop,
    and calling it from inside a running one is a RuntimeError.

    The call starts at ChooseSlot, as `tests/test_observers.py` does: driving
    Identify through the model first would add two turns and two ways to fail to
    an assertion that is about the log. What Identify DOES leave behind is put
    in the log the only way it ever gets there — one `find_patient` through the
    executor — because the reply that opens the call names the appointment the
    patient already has, and without that lookup's summary the grounding metric
    is being asked about a fact this shortened run never looked up. It is the
    identification made honest, not a fixture: the same executor, the same
    spec, the same masked summary a real Identify writes.

    The script stops the moment `book_slot` is in the log rather than running to
    its end, and carries one spare "sí, confirmo". Haiku sometimes answers "la
    primera que me ha dicho" with a clarifying question instead of calling
    `book_appointment`, which pushes the confirmation one turn out and leaves
    the `ConfirmTask` cancelled by the hang-up — a flaky test about the model's
    mood, when what is being pinned is the conversion.
    """
    tc = fake_context(TENANT, PROJECT)
    tc.customer = {"appointment_id": APPOINTMENT, **tc.adapters["agenda"].book[APPOINTMENT]}
    tc.prev_agent = stages.Identify(tc)
    attach_log(tc, MemoryStore())
    await tc.tools.call("find_patient", {"phone": tc.customer["phone"]})

    async with live_conversation(tc, stages.ChooseSlot(tc)) as call:
        for text in CALL:
            if _booked(tc):
                break
            await call.say(text)

    return replay.conversational_case_from(
        tc.log.store, tc.session_id, replay.descriptions_for(TENANT, PROJECT)
    )


def _booked(tc) -> bool:
    """Whether the irreversible write is already in the log — the call has nothing left to do."""
    return any(
        event.kind == "tool.call" and event.payload.get("tool") == "book_slot"
        for event in tc.log.events()
    )
