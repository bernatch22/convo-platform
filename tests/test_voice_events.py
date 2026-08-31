"""The audio path in the log: timed words, judged overlaps, murmurs that do not become replies.

No microphone and no provider: Soniox bills per second and ElevenLabs per
character, so a fake aligned transcript and constructed LiveKit events prove
the same wiring for nothing. What this suite is really guarding is the SDK
surface — event names, `TimedString.end_time`, `StopResponse` — which is the
half of ms-6 that breaks silently when the framework moves under us.
"""

from types import SimpleNamespace

import pytest
from livekit.agents import AgentSession, StopResponse
from livekit.agents.inference.interruption import OverlappingSpeechEvent
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.agents.types import TimedString
from livekit.agents.voice.events import AgentFalseInterruptionEvent, CloseEvent, CloseReason

from convo import sessions
from core.agents.base import TenantAgent
from core.barge_in import SPANISH_BACKCHANNELS, is_backchannel
from core.observability.observers import observe
from core.observability.voice import MAX_WORDS_PER_EVENT, observe_voice, recording_path
from core.state.attach import attach_log
from core.state.store import MemoryStore
from core.testing.harness import fake_context

pytestmark = pytest.mark.unit

OGG = "/tmp/console-recordings/session-08-30-2011/audio.ogg"


@pytest.fixture
async def wired() -> tuple[AgentSession, object]:
    """A real AgentSession with no model, its voice events observed into an in-memory log."""
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    session = AgentSession(llm=None, userdata=tc)
    observe(session, tc)
    observe_voice(session, tc)
    return session, tc


def kinds(tc) -> list[str]:
    return [event.kind for event in tc.log.events()]


def payloads(tc, kind: str) -> list[dict]:
    return [event.payload for event in tc.log.events() if event.kind == kind]


async def aligned(*words: tuple[str, float | None]):
    """A TTS transcription stream: a word per delta, timed unless its end_time is None."""
    for text, end_time in words:
        yield TimedString(text, end_time=end_time) if end_time is not None else text


async def drain(agent: TenantAgent, stream) -> list[str]:
    """Everything the node yielded, as plain strings — what the caller would have read."""
    return [str(delta) async for delta in agent.transcription_node(stream, {})]


def agent_for(tc, speaking: bool) -> TenantAgent:
    """A stage bound to `tc`, whose `session` says whether the agent holds the floor.

    `Agent.session` raises unless the agent is running inside an activity, and
    a running activity means a model. Subclassed rather than patched onto
    `TenantAgent`: a property written on the shared class outlives the test.
    """
    floor = SimpleNamespace(
        agent_state="speaking" if speaking else "listening", current_speech=None
    )

    class Stage(TenantAgent):
        @property
        def session(self):
            return floor

    return Stage(tc, instructions="test")


# ── the agent's own words, with their times ──────────────────────────────────


async def test_the_timed_words_of_a_sentence_reach_the_log_as_one_tts_word_event() -> None:
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    agent = agent_for(tc, speaking=True)

    said = await drain(agent, aligned(("Su ", 0.31), ("cita ", 0.62), ("es ", 0.8), ("hoy.", 1.14)))

    assert "".join(said) == "Su cita es hoy."  # the transcript is forwarded untouched
    assert payloads(tc, "tts.word") == [
        {
            "words": [
                {"w": "Su", "t1": 0.31},
                {"w": "cita", "t1": 0.62},
                {"w": "es", "t1": 0.8},
                {"w": "hoy.", "t1": 1.14},
            ]
        }
    ]


async def test_a_second_sentence_is_a_second_event_and_the_tail_flushes_at_the_end() -> None:
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    agent = agent_for(tc, speaking=True)

    await drain(agent, aligned(("Vale.", 0.4), ("Le ", 0.7), ("cambio", 1.0)))

    assert [len(event["words"]) for event in payloads(tc, "tts.word")] == [1, 2]


async def test_a_long_sentence_is_cut_into_batches_so_the_log_is_not_written_per_word() -> None:
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    agent = agent_for(tc, speaking=True)

    await drain(agent, aligned(*[(f"w{i} ", i / 10) for i in range(MAX_WORDS_PER_EVENT + 3)]))

    assert [len(event["words"]) for event in payloads(tc, "tts.word")] == [MAX_WORDS_PER_EVENT, 3]


async def test_a_word_with_no_alignment_is_forwarded_but_not_given_a_time() -> None:
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    agent = agent_for(tc, speaking=True)

    said = await drain(agent, aligned(("Su ", None), ("cita.", 0.9)))

    assert "".join(said) == "Su cita."
    assert payloads(tc, "tts.word") == [{"words": [{"w": "cita.", "t1": 0.9}]}]


def test_convo_sessions_show_renders_timed_words_as_word_at_time() -> None:
    words = [{"w": "Su", "t1": 0.31}, {"w": "cita", "t1": 0.62}]
    event = SimpleNamespace(kind="tts.word", payload={"words": words})

    assert sessions.render(event) == "Su@0.31 cita@0.62"


# ── the interruption events ──────────────────────────────────────────────────


async def test_a_false_interruption_and_an_overlap_reach_the_log(wired) -> None:
    session, tc = wired

    session.emit("agent_false_interruption", AgentFalseInterruptionEvent(resumed=True))
    session.emit(
        "overlapping_speech",
        OverlappingSpeechEvent(is_interruption=False, probability=0.1234, detection_delay=0.4567),
    )

    assert kinds(tc) == ["session.start", "interruption.false", "speech.overlap"]
    assert payloads(tc, "interruption.false") == [{"resumed": True}]
    assert payloads(tc, "speech.overlap") == [
        {"interruption": False, "agent_ended": False, "probability": 0.123, "delay": 0.457}
    ]


async def test_an_interim_transcript_is_still_not_logged_next_to_the_voice_events(wired) -> None:
    from livekit.agents.voice.events import UserInputTranscribedEvent

    session, tc = wired

    session.emit(
        "user_input_transcribed", UserInputTranscribedEvent(transcript="va", is_final=False)
    )
    session.emit(
        "user_input_transcribed", UserInputTranscribedEvent(transcript="vale", is_final=True)
    )

    assert kinds(tc) == ["session.start", "stt.final"]


# ── the barge-in filter ──────────────────────────────────────────────────────


def test_the_spanish_stoplist_reads_a_murmur_and_leaves_a_sentence_alone() -> None:
    assert is_backchannel("vale") and is_backchannel("¡Ajá!") and is_backchannel("sí sí")
    assert is_backchannel("de acuerdo") and is_backchannel("mm")
    assert not is_backchannel("vale, el jueves") and not is_backchannel("")
    assert "vale" in SPANISH_BACKCHANNELS


async def test_a_murmur_over_the_agents_voice_is_dropped_and_logged() -> None:
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    agent = agent_for(tc, speaking=True)

    with pytest.raises(StopResponse):
        await agent.on_user_turn_completed(
            ChatContext.empty(), ChatMessage(role="user", content=["sí sí"])
        )

    assert payloads(tc, "turn.backchannel") == [{"text": "sí sí"}]


async def test_a_real_sentence_over_the_agents_voice_is_answered() -> None:
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    agent = agent_for(tc, speaking=True)

    await agent.on_user_turn_completed(
        ChatContext.empty(), ChatMessage(role="user", content=["quiero cambiar la cita"])
    )

    assert "turn.backchannel" not in kinds(tc)


async def test_a_murmur_into_silence_is_answered_because_vale_alone_is_a_yes() -> None:
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    agent = agent_for(tc, speaking=False)

    await agent.on_user_turn_completed(
        ChatContext.empty(), ChatMessage(role="user", content=["vale"])
    )

    assert "turn.backchannel" not in kinds(tc)


async def test_a_project_brings_its_own_stoplist() -> None:
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    tc.project.backchannels = ["dale"]
    agent = agent_for(tc, speaking=True)
    try:
        with pytest.raises(StopResponse):
            await agent.on_user_turn_completed(
                ChatContext.empty(), ChatMessage(role="user", content=["Dale"])
            )
        await agent.on_user_turn_completed(
            ChatContext.empty(), ChatMessage(role="user", content=["vale"])
        )
    finally:
        tc.project.backchannels = []

    assert payloads(tc, "turn.backchannel") == [{"text": "Dale"}]


# ── the recording ────────────────────────────────────────────────────────────


async def test_session_end_carries_the_ogg_when_the_session_was_recorded(wired) -> None:
    session, tc = wired
    session._recorder_io = SimpleNamespace(output_path=OGG)

    session.emit("close", CloseEvent(reason=CloseReason.USER_INITIATED))

    assert payloads(tc, "session.end")[0]["audio"] == OGG


async def test_session_end_has_no_audio_key_when_nothing_was_recorded(wired) -> None:
    session, tc = wired

    session.emit("close", CloseEvent(reason=CloseReason.USER_INITIATED))

    assert "audio" not in payloads(tc, "session.end")[0]
    assert recording_path(session) is None
