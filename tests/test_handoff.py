"""Stages hand off with a summary: the next agent knows what happened, not the whole transcript."""

import pytest
from livekit.agents import AgentSession
from livekit.agents.voice import Agent

from convo.agents import TenantAgent
from convo.testing import fake_context

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """on_enter asks the model to speak; here there is no model, only the context to inspect."""
    monkeypatch.setattr(AgentSession, "generate_reply", lambda self, **kw: None)


class Identify(TenantAgent):
    def __init__(self, tc) -> None:
        super().__init__(tc, instructions="identify")

    def summary(self) -> str:
        return "El paciente es Ana García, cita el martes 1 a las 10:00."


class ChooseSlot(TenantAgent):
    def __init__(self, tc) -> None:
        super().__init__(tc, instructions="choose")


async def test_on_enter_writes_the_previous_stage_summary_into_the_chat_context() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    first, second = Identify(tc), ChooseSlot(tc)
    tc.prev_agent = first
    session = AgentSession(llm=None)

    await session.start(second)
    await session.aclose()

    texts = [item.text_content for item in second.chat_ctx.items if hasattr(item, "text_content")]
    assert "Ana García" in " ".join(t or "" for t in texts)
    assert tc.prev_agent is second


async def test_the_first_stage_enters_with_nothing_to_inherit() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    first = Identify(tc)
    session = AgentSession(llm=None)

    await session.start(first)
    await session.aclose()

    texts = [i.text_content or "" for i in first.chat_ctx.items if hasattr(i, "text_content")]
    meaningful = [t for t in texts if t and t != "identify"]  # instructions render as an item too
    assert meaningful == [], "nothing to inherit, and the date is not a message anybody said"

    reading = [i.output for i in first.chat_ctx.items if i.type == "function_call_output"]
    assert len(reading) == 1 and reading[0].startswith("Hoy es martes 1 de septiembre de 2026")


def test_hand_off_returns_the_next_stage_and_what_to_say() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    first, second = Identify(tc), ChooseSlot(tc)

    agent, said = first.hand_off(second, said="Perfecto, veamos qué día le viene bien.")

    assert isinstance(agent, Agent) and agent is second
    assert said.startswith("Perfecto")
