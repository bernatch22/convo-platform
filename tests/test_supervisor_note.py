"""What Anthropic actually receives when a supervisor whispers — rendered, not assumed.

`tests/test_supervisor_control.py` pins the mechanics against a fake session.
This file pins the two things only the REAL provider format can show, and both
are load-bearing for `tk-bc0122`:

1. the note arrives as an instruction IN the conversation, in position, and
   never as a caller's line the model could answer nor a block of the prompt;
2. the cached prefix is byte-identical before and after the whisper — the
   constraint that ruled out every "just put it in the system prompt" idea, and
   the reason a steer costs nothing at the cache.

And the third leg, keyless too: the paragraph that makes the model rank a
whisper above its own stage script is in every project's prefix.
"""

import asyncio

import pytest
from livekit.agents import AgentSession
from livekit.agents.llm._provider_format import anthropic as anthropic_format

from convo.prompting.protocols import STEER_PREFACE, SUPERVISOR_PROTOCOL
from convo.session.registry import load_registry
from convo.supervision.control import SupervisorControl
from convo.supervision.supervisor import STEER
from convo.testing import fake_context

pytestmark = pytest.mark.unit

SUP = "sup:berna"
NOTE = "no le pidas el teléfono, con el nombre nos basta"


async def opened_call(tc) -> tuple[AgentSession, object]:
    """The project's entry stage, started, with its greeting already in the history."""
    stage = tc.project.entry_agent(tc)
    session = AgentSession(llm=None)
    await session.start(stage)
    for _ in range(100):
        if any(getattr(item, "role", None) == "assistant" for item in session.history.items):
            break
        await asyncio.sleep(0.02)
    return session, stage


async def test_a_whisper_is_an_instruction_in_the_conversation_never_a_caller_turn() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    session, stage = await opened_call(tc)
    control = SupervisorControl(tc, session)

    await control.apply(STEER, SUP, {"text": NOTE})
    messages, extra = anthropic_format.to_chat_ctx(stage.chat_ctx)
    await session.aclose()

    said = [
        block.get("text", "")
        for message in messages
        for block in message["content"]
        if block.get("type") == "text"
    ]
    whispered = [text for text in said if NOTE in text]
    assert len(whispered) == 1, "the note reaches the model exactly once"
    assert whispered[0].startswith("<instructions>"), (
        "it is an instruction, not something a person said"
    )
    assert STEER_PREFACE.strip() in whispered[0], "and it says whose instruction it is"
    assert not any(NOTE in block for block in extra.system_messages or []), (
        "a whisper never enters the prompt itself"
    )


async def test_the_cached_prefix_is_byte_identical_before_and_after_a_whisper() -> None:
    """Criterion 2 of the card, decided without a key: the prefix cannot move."""
    tc = fake_context("clinica-norte", "reagendamiento")
    session, stage = await opened_call(tc)
    control = SupervisorControl(tc, session)

    _, before = anthropic_format.to_chat_ctx(stage.chat_ctx)
    await control.apply(STEER, SUP, {"text": NOTE})
    await control.apply(STEER, SUP, {"text": "y ofrécele el jueves por la tarde"})
    _, after = anthropic_format.to_chat_ctx(stage.chat_ctx)
    await session.aclose()

    assert after.system_messages == before.system_messages, (
        "two whispers and the cached prefix has not moved a byte"
    )


def test_every_project_teaches_its_persona_what_a_supervisor_note_is() -> None:
    """A persona that has never heard of supervisor notes ignores them (measured 0/3)."""
    for tenant_id, tenant in load_registry().items():
        for project_id, project in tenant.projects.items():
            tc = fake_context(tenant_id, project_id)
            for stage in project.stages(tc):
                assert SUPERVISOR_PROTOCOL in stage.instructions, (
                    f"{tenant_id}/{project_id}:{stage.stage_name()} "
                    "cannot be steered: its prompt never mentions the supervisor"
                )
