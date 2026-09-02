"""Whisper and takeover: the identity decides, the log remembers, the model never sees a hole.

Four claims are pinned here and each is one section below.

1. A steer changes the agent's next turn — and only when it came from an
   identity this deployment signed as `sup:`. The gate is one line in
   `SupervisorControl.apply`, and both roads (RPC, control-plane packet) go
   through it, so both are refused by the same line.
2. A takeover silences the agent: `StopResponse` on every turn while muted is
   the proof, because it is the framework's own "do not answer this one", and
   the turn still lands in the history for `release` to read back.
3. A steer never orphans a tool pair. The whisper swaps the agent's whole
   context, so a context that was mid-tool-call when it landed would be
   written back broken without `sanitize_tool_pairing`.
4. Every verb is in the caller's own log, continuing its `seq`.

Nothing here needs a key, a room or a model: the session is a fake with the
five attributes the control actually touches, which is itself the assertion
that supervision does not reach any further into the framework than that.
"""

import asyncio
import json
from typing import Any

import pytest
from livekit.agents import StopResponse
from livekit.agents.llm import ChatContext, FunctionCall, FunctionCallOutput
from livekit.rtc import RpcError

from convo.agents import TenantAgent
from convo.session.history import orphans
from convo.supervision import monitor
from convo.supervision.control import (
    STEER_PREFACE,
    NotASupervisor,
    SupervisorControl,
    UnknownVerb,
)
from convo.supervision.supervisor import RELEASE, STEER, TAKEOVER, TRANSFER
from convo.testing import fake_context

pytestmark = pytest.mark.unit

SUP = "sup:berna"
CALLER = "clinica-norte:u1"


# ── the fakes: exactly the surface a supervisor's verb touches ────────────────


class FakeAgent:
    """An agent that only remembers the contexts it was handed."""

    def __init__(self, chat_ctx: ChatContext | None = None) -> None:
        self.chat_ctx = chat_ctx if chat_ctx is not None else ChatContext()
        self.updates: list[ChatContext] = []

    async def update_chat_ctx(self, chat_ctx: ChatContext) -> None:
        self.updates.append(chat_ctx)
        self.chat_ctx = chat_ctx


class FakeInput:
    def __init__(self) -> None:
        self.audio_enabled = True

    def set_audio_enabled(self, enabled: bool) -> None:
        self.audio_enabled = enabled


class FakeOptions:
    def __init__(self) -> None:
        self.interruption = {"resume_false_interruption": True}


class FakeSession:
    """The five things `SupervisorControl` reads off a session, and nothing more."""

    def __init__(self, agent: FakeAgent, speaking: bool = False, running: bool = True) -> None:
        self.current_agent = agent
        self.agent_state = "speaking" if speaking else "listening"
        self.current_speech = object() if speaking else None
        self.input = FakeInput()
        self.options = FakeOptions()
        self.running = running
        self.interrupts = 0
        self.replies: list[dict[str, Any]] = []

    def interrupt(self, *, force: bool = False):
        if not self.running:
            raise RuntimeError("AgentSession isn't running")
        self.interrupts += 1
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        done.set_result(None)
        return done

    def generate_reply(self, **kwargs: Any) -> None:
        self.replies.append(kwargs)


class Invocation:
    """`RpcInvocationData` as the SFU builds it: the identity is off the JWT, not the payload."""

    def __init__(self, caller_identity: str, payload: dict[str, Any]) -> None:
        self.caller_identity = caller_identity
        self.payload = json.dumps(payload)


class Packet:
    """A data packet; `participant=None` is the SFU's word for "a server SDK sent this"."""

    def __init__(self, body: dict[str, Any], participant: Any = None) -> None:
        self.data = json.dumps(body).encode("utf-8")
        self.topic = monitor.TOPIC
        self.participant = participant


@pytest.fixture
def tc():
    return fake_context("clinica-norte", "reagendamiento")


@pytest.fixture
def agent() -> FakeAgent:
    return FakeAgent()


@pytest.fixture
def session(agent: FakeAgent) -> FakeSession:
    return FakeSession(agent)


@pytest.fixture
def control(tc, session: FakeSession) -> SupervisorControl:
    return SupervisorControl(tc, session)


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


class _Stage(TenantAgent):
    """A stage running outside any activity: `session` is the fake, as it is in a job."""

    def __init__(self, tc, session: FakeSession) -> None:
        super().__init__(tc, instructions="stage")
        self._live = session

    @property
    def session(self) -> Any:
        return self._live


class _Room:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}
        self.methods: dict[str, Any] = {}
        self.local_participant = self

    def on(self, event: str, handler: Any) -> None:
        self.handlers[event] = handler

    def register_rpc_method(self, name: str, handler: Any) -> None:
        self.methods[name] = handler


def _said(text: str):
    """A user turn as the framework hands it to `on_user_turn_completed`."""
    from livekit.agents.llm import ChatMessage

    return ChatMessage(role="user", content=[text])
