"""ConfirmTask speaks the platform's question as written; the model only hears the answer."""

import pytest
from livekit.agents import AgentSession

from core.agents import ConfirmTask
from core.testing import fake_context

pytestmark = pytest.mark.unit

QUESTION = "jueves 3 de septiembre a las nueve de la mañana con Dr. Hugo Ferrer, ¿lo confirmo?"


async def test_on_enter_says_the_question_verbatim_and_never_generates(monkeypatch) -> None:
    said: list[str] = []
    monkeypatch.setattr(AgentSession, "say", lambda self, text, **kw: said.append(text))
    monkeypatch.setattr(
        AgentSession,
        "generate_reply",
        lambda self, **kw: pytest.fail("ConfirmTask must not generate its opening line"),
    )
    tc = fake_context("clinica-norte", "reagendamiento")
    task = ConfirmTask(tc, question=QUESTION, tool="book_slot", args={"slot_id": "sl-1"})
    session = AgentSession(llm=None)

    await session.start(task)
    await session.aclose()

    assert said == [QUESTION]
    kinds = [e.kind for e in tc.log.events()]
    assert kinds[-1] == "confirm.request"
    assert tc.log.events()[-1].payload["question"] == QUESTION


async def test_the_instructions_tell_the_model_the_question_was_already_asked() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    task = ConfirmTask(tc, question=QUESTION, tool="book_slot", args={})

    assert "Ya has hecho la pregunta" in task.instructions
    assert QUESTION in task.instructions
