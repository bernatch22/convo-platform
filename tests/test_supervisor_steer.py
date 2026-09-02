"""A steer changes the next turn; a takeover silences the agent until release."""

import json

import pytest
from livekit.agents import StopResponse
from livekit.agents.llm import ChatContext
from livekit.rtc import RpcError

from convo.supervision import monitor
from convo.supervision.control import STEER_PREFACE, NotASupervisor, SupervisorControl, UnknownVerb
from convo.supervision.supervisor import STEER
from tests.fixtures.supervision import (  # noqa: F401  (fixtures)
    CALLER,
    SUP,
    FakeSession,
    Invocation,
    _said,
    _Stage,
    agent,
    control,
    session,
    tc,
)

pytestmark = pytest.mark.unit


# ── 1. a steer changes the next turn, and only a supervisor may send one ──────


async def test_a_steer_from_a_supervisor_lands_in_the_agents_own_context(control, agent) -> None:
    await control.apply(STEER, SUP, {"text": "ofrécele el jueves por la tarde"})

    (swapped,) = agent.updates
    assert swapped.items[-1].role == "system"
    assert swapped.items[-1].text_content == STEER_PREFACE + "ofrécele el jueves por la tarde"


async def test_a_steer_from_any_other_identity_is_refused_and_changes_nothing(
    control, agent, tc
) -> None:
    for identity in (CALLER, "observer:ab12", "", "supervisor:berna"):
        with pytest.raises(NotASupervisor):
            await control.apply(STEER, identity, {"text": "dile que no"})

    assert agent.updates == []
    assert [event.kind for event in tc.log.events() if event.kind == STEER] == []


async def test_the_rpc_handler_answers_a_supervisor_and_refuses_everybody_else(control) -> None:
    """The handler is the browser's door; the gate behind it is the same one."""
    handle = monitor.verb_handler(control, STEER)

    answered = await handle(Invocation(SUP, {"text": "sé más breve"}))

    assert json.loads(answered)["verb"] == STEER
    with pytest.raises(RpcError, match="not a supervisor"):
        await handle(Invocation(CALLER, {"text": "sé más breve"}))


async def test_an_empty_or_unknown_steer_comes_back_as_an_error_the_desk_can_read(control) -> None:
    handle = monitor.verb_handler(control, STEER)

    with pytest.raises(RpcError, match="says nothing"):
        await handle(Invocation(SUP, {"text": "   "}))
    with pytest.raises(RpcError, match="unknown steer mode"):
        await handle(Invocation(SUP, {"text": "algo", "mode": "shout"}))


async def test_a_verb_this_build_does_not_implement_is_named_not_swallowed(control) -> None:
    """A newer desk talking to an older worker gets a refusal that names the verb."""
    with pytest.raises(UnknownVerb, match="supervisor.conference"):
        await control.apply("supervisor.conference", SUP, {})


async def test_a_steer_mid_sentence_waits_for_the_turn_boundary(tc, agent) -> None:
    """Swapping the context under a streaming generation is how a tool call loses its result."""
    control = SupervisorControl(tc, FakeSession(agent, speaking=True))

    answered = await control.steer(SUP, "no le ofrezcas el viernes")

    assert answered["queued"] is True
    assert agent.updates == []

    await control.flush(agent)  # what TenantAgent.on_user_turn_completed does

    assert agent.chat_ctx.items[-1].text_content.endswith("no le ofrezcas el viernes")


async def test_inject_and_speak_asks_for_a_turn_while_inject_only_waits_for_one(tc, agent) -> None:
    control = SupervisorControl(tc, FakeSession(agent))

    await control.steer(SUP, "pregúntale el teléfono", mode="inject")
    assert control.session.replies == []

    await control.steer(SUP, "pregúntaselo ahora", mode="inject_and_speak")
    assert len(control.session.replies) == 1
    assert "supervisor" in control.session.replies[0]["instructions"]


# ── 2. takeover silences the agent; release brings it back knowing what it missed ──


async def test_takeover_cuts_the_sentence_and_holds_off_the_frameworks_own_resume(
    control, session
) -> None:
    answered = await control.takeover(SUP)

    assert answered["muted"] is True and answered["interrupted"] is True
    assert session.interrupts == 1
    assert session.options.interruption["resume_false_interruption"] is False


async def test_while_a_human_holds_the_line_the_agent_answers_nothing(tc, control, session) -> None:
    """The proof of "no auto-reply while muted": the framework's own skip-this-turn."""
    tc.supervisor = control
    stage = _Stage(tc, session)
    await control.takeover(SUP)

    with pytest.raises(StopResponse):
        await stage.on_user_turn_completed(ChatContext(), _said("necesito hablar con alguien"))


async def test_the_agent_answers_again_once_the_line_is_handed_back(tc, control, session) -> None:
    tc.supervisor = control
    stage = _Stage(tc, session)
    await control.takeover(SUP)
    await control.release(SUP)

    await stage.on_user_turn_completed(ChatContext(), _said("necesito hablar con alguien"))


async def test_release_resumes_the_agent_with_the_human_interval_in_context(
    control, agent, session
) -> None:
    await control.takeover(SUP)
    agent.chat_ctx.add_message(role="user", content="le paso con mi compañera, un momento")

    answered = await control.release(SUP)

    assert answered["heard"] is True and answered["turns"] == 1
    assert "un momento" in agent.chat_ctx.items[-1].text_content
    assert session.replies[-1]["instructions"].startswith("Vuelves a llevar")
    assert session.options.interruption["resume_false_interruption"] is True


async def test_an_interval_that_never_reached_the_history_is_said_to_be_missing(
    control, agent
) -> None:
    """agents#5038: interrupted text can drop out. An agent that invents it is the worse bug."""
    await control.takeover(SUP)

    answered = await control.release(SUP)

    assert answered["heard"] is False
    assert "no quedó en esta transcripción" in agent.chat_ctx.items[-1].text_content


async def test_a_deaf_takeover_switches_the_ears_off_and_release_switches_them_back(
    control, session
) -> None:
    await control.takeover(SUP, deaf=True)
    assert session.input.audio_enabled is False

    await control.release(SUP)
    assert session.input.audio_enabled is True


async def test_the_default_takeover_keeps_the_stt_running(control, session) -> None:
    """Because the interval has to be transcribed for release to hand it back."""
    await control.takeover(SUP)

    assert session.input.audio_enabled is True


async def test_a_second_takeover_from_a_desk_that_lost_its_socket_changes_nothing(
    control, session
) -> None:
    await control.takeover(SUP)
    answered = await control.takeover(SUP)

    assert answered["already"] is True
    assert session.interrupts == 1


async def test_releasing_a_line_nobody_took_is_a_no_op_not_a_reply(control, session) -> None:
    answered = await control.release(SUP)

    assert answered["already"] is True
    assert session.replies == []
