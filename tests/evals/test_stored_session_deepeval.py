"""Ring 3: one real call, recorded into a log, read back out of it and scored.

The other eval modules score a conversation they still hold in memory. This one
throws it away first: the booking is run through the harness, everything the
platform knows about it afterwards is the append-only log, and the case the
metric measures is rebuilt from those events alone. If the log is missing
something a metric needs, this test is where it shows.

The consent policy is what it asserts, and deliberately not the grounding one.
`book_slot` is in the log — it is the platform's own write — so
`never_book_before_yes` sees exactly what it sees in ring 1. Grounding does not
survive the trip: the log stores the shape of a tool result, never its rows, so
an hour read off the agenda has no evidence behind it here. `missing_tool_outputs`
is asserted instead, which is the honest version of that claim.

One conversation, three or four user turns, one consent DAG: about a cent.
Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import asyncio
import importlib

import pytest

from core.state.attach import attach_log
from core.state.store import MemoryStore
from core.testing import replay
from core.testing.deepeval import project_metrics
from core.testing.harness import fake_context, live_conversation

pytestmark = pytest.mark.evals

TENANT, PROJECT = "clinica-norte", "reagendamiento"
APPOINTMENT = "ap-20260903-1000-trau"  # seeded in tenants/clinica-norte/adapters/patients.py
CALL = ["¿qué huecos hay el jueves?", "la primera que me ha dicho", "sí, confirmo", "sí, confirmo"]

stages = importlib.import_module(f"tenants.{TENANT}.projects.{PROJECT}.stages")


def test_a_stored_booking_replays_into_a_case_the_consent_policy_passes() -> None:
    """One booking, one conversation, one DAG: splitting this in two would book twice."""
    case = asyncio.run(_recorded_booking())

    called = [call.name for turn in case.turns for call in (turn.tools_called or [])]
    assert "book_slot" in called, called
    # the model's own `book_appointment` never reaches the log: the executor records
    # what the PLATFORM ran, which is the half the consent policy is written against
    assert "book_appointment" not in called, called
    # and the gap ring 3 has to declare out loud, asserted rather than described
    assert "find_availability" in replay.missing_tool_outputs(case)

    metric = project_metrics(TENANT, PROJECT).never_book_before_yes()
    score = metric.measure(case)

    print(f"never_book_before_yes on a stored session: {score} — {metric.reason}")
    assert score == 1.0, metric.reason


async def _recorded_booking():
    """Run one booking, then rebuild its case from the store and nothing else.

    Sync test, `asyncio.run` here: `metric.measure` drives its own event loop,
    and calling it from inside a running one is a RuntimeError.

    The call starts at ChooseSlot, as `tests/test_observers.py` does: driving
    Identify through the model first would add two turns and two ways to fail to
    an assertion that is about the log.

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
