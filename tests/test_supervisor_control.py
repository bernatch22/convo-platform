"""A steer never orphans a tool pair, every verb lands in the log, and the control-plane road."""

import asyncio

import pytest
from livekit.agents.llm import ChatContext, FunctionCall, FunctionCallOutput

from convo.session.history import orphans
from convo.supervision import monitor
from convo.supervision.control import SupervisorControl
from convo.supervision.supervisor import RELEASE, STEER, TAKEOVER, TRANSFER
from tests.fixtures.supervision import (  # noqa: F401  (fixtures)
    CALLER,
    SUP,
    FakeAgent,
    FakeSession,
    Packet,
    _Room,
    agent,
    control,
    session,
    tc,
)

pytestmark = pytest.mark.unit


# ── 3. a steer never orphans a tool pair ─────────────────────────────────────


async def test_a_steer_that_lands_mid_tool_call_leaves_no_orphan_behind(tc) -> None:
    chat_ctx = ChatContext()
    chat_ctx.add_message(role="user", content="quiero cambiar la cita")
    chat_ctx.insert(FunctionCall(call_id="c1", name="check_slots", arguments="{}"))
    agent = FakeAgent(chat_ctx)
    control = SupervisorControl(tc, FakeSession(agent))

    await control.steer(SUP, "ofrécele solo por la tarde")

    (swapped,) = agent.updates
    assert orphans(swapped) == []
    assert swapped.items[-1].text_content.endswith("ofrécele solo por la tarde")


async def test_a_finished_tool_exchange_survives_the_swap_whole(tc) -> None:
    chat_ctx = ChatContext()
    chat_ctx.insert(FunctionCall(call_id="c1", name="check_slots", arguments="{}"))
    chat_ctx.insert(
        FunctionCallOutput(call_id="c1", name="check_slots", output="[]", is_error=False)
    )
    agent = FakeAgent(chat_ctx)

    await SupervisorControl(tc, FakeSession(agent)).steer(SUP, "cierra la llamada")

    (swapped,) = agent.updates
    assert [item.type for item in swapped.items[:2]] == ["function_call", "function_call_output"]


# ── 4. every verb in the caller's own log, continuing its seq ─────────────────


async def test_every_verb_appends_to_the_callers_log_in_order(control, tc, agent) -> None:
    """The caller's own sequence continues: one call is one story, whoever is on it."""
    opened = tc.log.seq
    await control.steer(SUP, "ofrécele el jueves")
    await control.takeover(SUP)
    agent.chat_ctx.add_message(role="user", content="le atiendo yo")
    await control.release(SUP)

    assert [(event.seq, event.kind) for event in tc.log.events()[opened:]] == [
        (opened + 1, STEER),
        (opened + 2, TAKEOVER),
        (opened + 3, RELEASE),
    ]


async def test_the_steer_event_carries_who_whispered_what_and_how(control, tc) -> None:
    await control.steer(SUP, "sé más breve", mode="inject_and_speak")

    (event,) = [e for e in tc.log.events() if e.kind == STEER]
    assert event.payload == {"identity": SUP, "mode": "inject_and_speak", "text": "sé más breve"}


async def test_the_takeover_and_release_events_say_what_the_human_did(control, tc, agent) -> None:
    await control.takeover(SUP)
    agent.chat_ctx.add_message(role="user", content="le atiendo yo")
    await control.release(SUP)

    kinds = {event.kind: event.payload for event in tc.log.events()}
    assert kinds[TAKEOVER] == {"identity": SUP, "deaf": False, "interrupted": True}
    assert kinds[RELEASE] == {"identity": SUP, "turns": 1, "text": ["le atiendo yo"]}


# ── the control-plane road: the same gate, the same handler ───────────────────


async def test_a_verb_on_the_supervisor_topic_reaches_the_control(control, tc, agent) -> None:
    watch = monitor.SupervisorWatch(tc, control)

    spawned = watch.on_packet(Packet({"verb": "steer", "identity": SUP, "text": "ve al grano"}))
    await asyncio.sleep(0)

    assert spawned is True
    assert agent.chat_ctx.items[-1].text_content.endswith("ve al grano")


async def test_a_participant_cannot_forge_a_verb_on_that_topic(control, tc, agent) -> None:
    watch = monitor.SupervisorWatch(tc, control)
    forged = Packet({"verb": "takeover", "identity": SUP}, participant=object())

    assert watch.on_packet(forged) is False
    assert control.muted is False


async def test_a_verb_naming_a_non_supervisor_is_refused_on_that_road_too(control, tc) -> None:
    watch = monitor.SupervisorWatch(tc, control)

    watch.on_packet(Packet({"verb": "takeover", "identity": CALLER}))
    await asyncio.sleep(0)

    assert control.muted is False


async def test_a_job_with_no_control_drops_the_verb_instead_of_crashing(tc) -> None:
    """The console has a watch and no session to steer; nobody should write an `if` about it."""
    watch = monitor.SupervisorWatch(tc)

    assert watch.on_packet(Packet({"verb": "steer", "identity": SUP, "text": "hola"})) is False


def test_the_rpc_methods_are_registered_under_their_audit_names(control) -> None:
    """One string per verb: the RPC method a browser calls IS the kind in the log."""
    room = _Room()

    taken = monitor.register_verbs(room, control)

    assert taken == (STEER, TAKEOVER, RELEASE, TRANSFER)
    assert sorted(room.methods) == [
        "supervisor.release",
        "supervisor.steer",
        "supervisor.takeover",
        "supervisor.transfer",
    ]


def test_watching_a_room_with_a_control_wires_both_roads(tc, control) -> None:
    room = _Room()

    watch = monitor.watch_supervisors(room, tc, control)

    assert room.handlers["data_received"] == watch.on_packet
    assert len(room.methods) == 4
