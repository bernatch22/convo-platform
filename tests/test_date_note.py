"""The model knows what day it is — as a clock reading it can read, never as a turn it answers.

Three things are pinned here, all without a key. The reading says what a person
would say. The session writes it once. And, the regression this file exists for:
once the context is rendered for Anthropic, the opening line of the call is the
project's greeting and NOTHING in the request puts the date in a caller's mouth
or inside the cached system prefix.
"""

import asyncio
from datetime import datetime

import pytest
from livekit.agents import AgentSession
from livekit.agents.llm._provider_format import anthropic as anthropic_format

from convo.agents.clock import CLOCK_TOOL, date_note
from convo.testing import fake_context

pytestmark = pytest.mark.unit

FROZEN = datetime(2026, 9, 1, 10, 30)  # the harness's Tuesday
THE_DAY = "Hoy es martes 1 de septiembre de 2026"


@pytest.fixture(autouse=True)
def silent_model(monkeypatch):
    monkeypatch.setattr(AgentSession, "generate_reply", lambda self, **kw: None)


async def opened_call(tc) -> tuple[AgentSession, object]:
    """Start the project's entry stage and wait for its greeting to land in the history.

    `session.say` schedules the line; the chat context has it a tick later, so a
    test that reads the context the instant `start` returns reads it half-built.
    """
    stage = tc.project.entry_agent(tc)
    session = AgentSession(llm=None)
    await session.start(stage)
    for _ in range(100):
        if any(getattr(item, "role", None) == "assistant" for item in session.history.items):
            break
        await asyncio.sleep(0.02)
    return session, stage


def test_the_note_reads_like_a_person_says_it() -> None:
    assert (
        date_note(FROZEN.date(), FROZEN.time())
        == "Hoy es martes 1 de septiembre de 2026 y son las 10:30."
    )
    assert date_note(FROZEN.date()).startswith("Hoy es martes 1 de septiembre de 2026.")


async def test_the_clock_tool_recomputes_every_call() -> None:
    from datetime import datetime as dt

    tc = fake_context("clinica-norte", "reagendamiento")
    ticks = iter([dt(2026, 9, 1, 10, 30), dt(2026, 9, 1, 10, 41)])
    tc.clock = lambda: next(ticks)
    stage = tc.project.entry_agent(tc)

    first = await stage.fecha_y_hora_actual(None)
    second = await stage.fecha_y_hora_actual(None)

    assert first.endswith("10:30.") and second.endswith("10:41."), "never cached, read per call"


async def test_the_entry_stage_reads_the_clock_once_and_handoffs_never_repeat_it() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    tc.clock = lambda: FROZEN
    first = tc.project.entry_agent(tc)
    session = AgentSession(llm=None)

    await session.start(first)
    reading = [item for item in first.chat_ctx.items if item.type == "function_call_output"]
    assert [item.name for item in reading] == [CLOCK_TOOL]
    assert THE_DAY in reading[0].output
    await session.aclose()

    second = tc.project.stages(tc)[1]
    tc.prev_agent = first
    session2 = AgentSession(llm=None)
    await session2.start(second)
    await session2.aclose()
    texts = [i.text_content or "" for i in second.chat_ctx.items if hasattr(i, "text_content")]
    assert not any("Hoy es" in t for t in texts), "the reading is taken once per session"


async def test_the_first_thing_the_agent_says_is_the_greeting() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    tc.clock = lambda: FROZEN
    session, stage = await opened_call(tc)

    spoken = [
        item.text_content
        for item in stage.chat_ctx.items
        if item.type == "message" and item.role == "assistant"
    ]
    await session.aclose()

    assert spoken[:1] == [tc.project.greeting], "the warm greeting opens the call, nothing else"


async def test_anthropic_never_sees_the_date_as_a_caller_turn_nor_in_the_cached_prefix() -> None:
    """The regression: a `system` note became a USER message and Haiku answered it.

    `convert_mid_conversation_instructions` (livekit-agents 1.7.1) keeps only
    the first system item as one and rewrites the rest with `role="user"`, so
    the date arrived as the caller's opening line. Rendering the real context
    through the real provider formatter is the only place that shows it.
    """
    tc = fake_context("clinica-norte", "reagendamiento")
    tc.clock = lambda: FROZEN
    session, stage = await opened_call(tc)
    await session.aclose()

    messages, extra = anthropic_format.to_chat_ctx(stage.chat_ctx)

    said_by_a_person = [
        block.get("text", "")
        for message in messages
        for block in message["content"]
        if block.get("type") == "text"
    ]
    assert not any("Hoy es" in text for text in said_by_a_person), "nobody says the date"
    assert not any("Hoy es" in text for text in extra.system_messages or []), (
        "the cached prefix must stay byte-identical from one day to the next"
    )
    results = [
        block
        for message in messages
        for block in message["content"]
        if block.get("type") == "tool_result"
    ]
    assert len(results) == 1 and THE_DAY in results[0]["content"], "it arrives as evidence"
