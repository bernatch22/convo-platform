"""Observers: the framework's session events become the log's own kinds, in order, with seq.

Two halves, on purpose. The first feeds constructed LiveKit events to a real
`AgentSession` and reads the log — no model, no money, and it fails the day an
event name or a payload field changes under us, which is the whole risk this
module carries. The second runs one real conversation through Haiku and asserts
the shape of a booking end to end.
"""

import importlib

import pytest
from livekit.agents import AgentSession
from livekit.agents.llm import ChatMessage, FunctionCall, FunctionCallOutput
from livekit.agents.metrics import AgentSessionUsage, LLMModelUsage
from livekit.agents.voice.events import (
    AgentStateChangedEvent,
    CloseEvent,
    CloseReason,
    ConversationItemAddedEvent,
    ErrorEvent,
    FunctionToolsExecutedEvent,
    UserInputTranscribedEvent,
)

from convo import sessions
from core.observability import prices
from core.observability.observers import observe, outcome_of, turn_metrics
from core.state.attach import attach_log, close_log
from core.state.store import MemoryStore
from core.testing.harness import fake_context, run_conversation
from core.tools.saga import Saga, SagaFailed
from tests.conftest import needs_llm

pytestmark = pytest.mark.unit

APPOINTMENT = "ap-20260903-1000-trau"  # seeded in tenants/clinica-norte/adapters/patients.py
PATIENT = "Ana García Ruiz"  # the name that must not appear in an audit line
# The kinds an operator audits, as opposed to the transcript. A turn IS what was
# said — the agent greets the patient by name and the replay eval reads it back —
# so the no-PII rule is about the lines that describe the machine, not the call.
AUDITED = ("tool.", "confirm.", "saga.", "stage.")
stages = importlib.import_module("tenants.clinica-norte.projects.reagendamiento.stages")

HAIKU_USAGE = AgentSessionUsage(
    model_usage=[
        LLMModelUsage(
            provider="anthropic",
            model="claude-haiku-4-5",
            input_tokens=10_000,  # the WHOLE prompt: fresh + cached + written
            input_cached_tokens=8_000,
            input_cache_creation_tokens=1_000,
            output_tokens=500,
        )
    ]
)


@pytest.fixture
async def wired() -> tuple[AgentSession, object, MemoryStore]:
    """A real AgentSession with no model, observing a context whose log is in memory.

    Async on purpose: `AgentSession.__init__` calls `asyncio.get_event_loop()`,
    which raises in a sync test that runs before any other test opened a loop.
    """
    store = MemoryStore()
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), store)
    session = AgentSession(llm=None, userdata=tc)
    observe(session, tc)
    return session, tc, store


def kinds(tc) -> list[str]:
    return [event.kind for event in tc.log.events()]


def payload(tc, kind: str) -> dict:
    return next(event.payload for event in tc.log.events() if event.kind == kind)


# ── the event bridge, without a model ────────────────────────────────────────


async def test_a_user_turn_and_an_agent_turn_are_logged_with_their_latencies(wired) -> None:
    session, tc, _ = wired

    session.emit(
        "conversation_item_added",
        ConversationItemAddedEvent(item=ChatMessage(role="user", content=["quiero cambiarla"])),
    )
    session.emit(
        "conversation_item_added",
        ConversationItemAddedEvent(
            item=ChatMessage(
                role="assistant",
                content=["Claro, ¿me dice su DNI?"],
                metrics={"llm_node_ttft": 0.4123, "e2e_latency": 1.2, "playback_latency": 9.9},
            )
        ),
    )

    assert kinds(tc) == ["session.start", "turn.user", "turn.agent"]
    assert payload(tc, "turn.user") == {"text": "quiero cambiarla"}
    # rounded to ms, and only the five latencies an operator reads
    assert payload(tc, "turn.agent")["metrics"] == {"llm_node_ttft": 0.412, "e2e_latency": 1.2}


async def test_only_the_final_transcript_reaches_the_log(wired) -> None:
    session, tc, _ = wired

    session.emit(
        "user_input_transcribed",
        UserInputTranscribedEvent(transcript="el jue", is_final=False),
    )
    session.emit(
        "user_input_transcribed",
        UserInputTranscribedEvent(transcript="el jueves", is_final=True, language="es"),
    )

    assert kinds(tc) == ["session.start", "stt.final"]
    assert payload(tc, "stt.final") == {"text": "el jueves", "language": "es"}


async def test_a_state_change_and_a_batch_of_tools_are_one_line_each(wired) -> None:
    session, tc, _ = wired
    call = FunctionCall(call_id="c1", name="find_availability", arguments="{}")
    output = FunctionCallOutput(call_id="c1", name="find_availability", output="ok", is_error=False)

    session.emit(
        "agent_state_changed",
        AgentStateChangedEvent(old_state="listening", new_state="thinking"),
    )
    session.emit(
        "function_tools_executed",
        FunctionToolsExecutedEvent(function_calls=[call], function_call_outputs=[output]),
    )

    assert kinds(tc) == ["session.start", "state", "tools.executed"]
    assert payload(tc, "state") == {"from": "listening", "to": "thinking"}
    # a count, never the arguments again: the executor already logged them masked
    assert payload(tc, "tools.executed") == {"count": 1}


async def test_a_provider_error_is_logged_for_a_developer(wired) -> None:
    session, tc, _ = wired

    session.emit("error", ErrorEvent(error=RuntimeError("overloaded"), source=object()))

    assert payload(tc, "error")["error"] == "RuntimeError('overloaded')"


async def test_the_close_carries_the_outcome_and_what_the_session_cost(wired, monkeypatch) -> None:
    session, tc, store = wired
    monkeypatch.setattr(type(session), "usage", property(lambda self: HAIKU_USAGE))

    session.emit("close", CloseEvent(reason=CloseReason.USER_INITIATED))
    close_log(tc, report={"chat_history": {"items": []}})

    end = payload(tc, "session.end")
    assert end["outcome"] == "completed"
    assert end["cost"]["eur"] > 0
    assert end["cost"]["models"][0]["model"] == "claude-haiku-4-5"
    # the row the CLI reads carries the same outcome and the framework's report
    assert store.session(tc.session_id).outcome == "completed"
    assert store.session(tc.session_id).report == {"chat_history": {"items": []}}


@pytest.mark.parametrize(
    ("reason", "error", "expected"),
    [
        (CloseReason.USER_INITIATED, None, "completed"),
        (CloseReason.TASK_COMPLETED, None, "completed"),
        (CloseReason.PARTICIPANT_DISCONNECTED, None, "dropped"),
        (CloseReason.JOB_SHUTDOWN, None, "dropped"),
        (CloseReason.ERROR, None, "error"),
    ],
)
def test_every_close_reason_maps_to_one_of_three_outcomes(reason, error, expected) -> None:
    assert outcome_of(CloseEvent(reason=reason, error=error)) == expected


async def test_a_context_without_a_log_is_simply_not_observed() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    tc.log = None

    observe(AgentSession(llm=None, userdata=tc), tc)  # must not raise


def test_a_turn_that_measured_nothing_carries_no_metrics_key() -> None:
    assert turn_metrics(None) == {}
    assert turn_metrics({"provider_request_ids": ["req_1"]}) == {}


# ── stage, confirm and saga, without a model ─────────────────────────────────


async def test_a_failed_saga_logs_the_failure_every_undo_and_a_summary() -> None:
    """Cancel the real appointment, then fail the SMS: the cancel has to be put back."""
    tc = attach_log(fake_context("clinica-norte", "reagendamiento"), MemoryStore())
    saga = (
        Saga(tc)
        .step("cancel_slot", {"appointment_id": APPOINTMENT})
        .step("send_sms", {"phone": "", "text": "su cita ha cambiado"})
    )

    with pytest.raises(SagaFailed):
        await saga.run()  # an SMS with no number is refused by the gateway

    saga_kinds = [kind for kind in kinds(tc) if kind.startswith("saga.")]
    assert saga_kinds == ["saga.fail", "saga.compensated", "saga.rolled_back"]
    # the undo is a tool call like any other, so the executor logs it in between
    assert kinds(tc)[-3:] == ["tool.result", "saga.compensated", "saga.rolled_back"]
    assert payload(tc, "saga.fail")["step"] == "send_sms"
    assert payload(tc, "saga.compensated") == {"step": "cancel_slot", "undo": "rebook_slot"}
    assert payload(tc, "saga.rolled_back")["failed_at"] == "send_sms"
    assert payload(tc, "saga.rolled_back")["compensated"] == ["cancel_slot"]


def test_the_price_table_bills_a_cached_prompt_once_not_three_times() -> None:
    cost = prices.session_cost(HAIKU_USAGE)

    # fresh 1000 + cached 8000 + written 1000 + output 500, each at its own rate
    expected = (1_000 * 1.00 + 8_000 * 0.10 + 1_000 * 1.25 + 500 * 5.00) / 1_000_000
    assert cost["eur"] == pytest.approx(expected * prices.USD_EUR, rel=1e-6)
    assert cost["unpriced"] == []


def test_a_model_with_no_price_is_named_never_guessed() -> None:
    usage = AgentSessionUsage(
        model_usage=[LLMModelUsage(provider="acme", model="mystery-1", input_tokens=1_000)]
    )

    assert prices.session_cost(usage) == {"eur": 0.0, "models": [], "unpriced": ["acme/mystery-1"]}


def test_a_price_is_found_by_model_because_provider_is_the_base_url_host() -> None:
    """livekit-agents 1.7.1 reports `api.anthropic.com` as the provider, not `anthropic`.

    A table keyed on that string matches nothing and reports every call as
    free — a silent zero is the worst possible failure for a cost line.
    """
    usage = AgentSessionUsage(
        model_usage=[
            LLMModelUsage(
                provider="api.anthropic.com",
                model="claude-haiku-4-5",
                input_tokens=1_000,
                output_tokens=100,
            )
        ]
    )

    cost = prices.session_cost(usage)
    assert cost["eur"] > 0 and cost["unpriced"] == []
    assert cost["models"][0]["provider"] == "api.anthropic.com"


# ── one real conversation ────────────────────────────────────────────────────


@needs_llm
async def test_a_booking_writes_the_whole_story_in_seq_order(capsys) -> None:
    """One real call that books, read back as the log an operator would open.

    It starts at ChooseSlot, where `tests/test_stages.py` starts its own booking
    tests: driving Identify through the model first would add two turns and two
    ways to fail to an assertion that is about the log, not about identification.
    """
    tc = identified_context()

    await run_conversation(
        tc,
        ["¿qué huecos hay el jueves?", "la primera que me ha dicho", "sí, confirmo"],
        stages.ChooseSlot(tc),
    )
    story = kinds(tc)

    assert story[0] == "session.start"
    assert story[-1] == "session.end"
    assert [event.seq for event in tc.log.events()] == list(range(1, len(story) + 1))
    for kind in ("stage.enter", "turn.user", "turn.agent", "tool.call", "tool.result"):
        assert kind in story, story
    assert first(story, "stage.enter") < first(story, "turn.agent")
    assert first(story, "tool.call") < first(story, "tool.result")
    assert first(story, "confirm.request") < first(story, "confirm.granted")
    # nothing irreversible before the yes, and the log is what proves it
    assert first(story, "confirm.granted") < book_slot_at(tc)
    assert first(story, "confirm.granted") < first(story, "stage.handoff")

    audited = [e.payload for e in tc.log.events() if e.kind.startswith(AUDITED)]
    assert PATIENT not in str(audited), audited  # masked by value, not by argument name

    end = payload(tc, "session.end")
    assert end["outcome"] == "completed"
    assert end["cost"]["eur"] > 0, end["cost"]
    assert end["cost"]["unpriced"] == []

    sessions.show_session(tc.log.store, tc.session_id)
    printed = capsys.readouterr().out
    assert "turn.agent" in printed and "ttft=" in printed
    assert "confirm.granted" in printed


def identified_context():
    """A context past Identify: Ana García is found and the cita she has is known."""
    tc = fake_context("clinica-norte", "reagendamiento")
    tc.customer = {"appointment_id": APPOINTMENT, **tc.adapters["agenda"].book[APPOINTMENT]}
    tc.prev_agent = stages.Identify(tc)
    return attach_log(tc, MemoryStore())


def first(story: list[str], kind: str) -> int:
    assert kind in story, f"{kind} never happened: {story}"
    return story.index(kind)


def book_slot_at(tc) -> int:
    """The position of the irreversible call itself, which the executor logged."""
    for index, event in enumerate(tc.log.events()):
        if event.kind == "tool.call" and event.payload.get("tool") == "book_slot":
            return index
    raise AssertionError("book_slot never ran")
