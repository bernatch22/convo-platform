"""The model knows what day it is: one note per session, in the messages, cache untouched."""

from datetime import datetime

import pytest
from livekit.agents import AgentSession

from core.dates_note import date_note
from core.testing import fake_context

pytestmark = pytest.mark.unit

FROZEN = datetime(2026, 9, 1, 10, 30)  # the harness's Tuesday


@pytest.fixture(autouse=True)
def silent_model(monkeypatch):
    monkeypatch.setattr(AgentSession, "generate_reply", lambda self, **kw: None)


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


async def test_the_entry_stage_writes_the_note_once_and_handoffs_never_repeat_it() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    tc.clock = lambda: FROZEN
    first = tc.project.entry_agent(tc)
    session = AgentSession(llm=None)

    await session.start(first)
    texts = [i.text_content or "" for i in first.chat_ctx.items if hasattr(i, "text_content")]
    assert any("Hoy es martes 1 de septiembre de 2026" in t for t in texts)

    second = tc.project.stages(tc)[1]
    tc.prev_agent = first
    await session.aclose()
    session2 = AgentSession(llm=None)
    await session2.start(second)
    await session2.aclose()
    texts2 = [i.text_content or "" for i in second.chat_ctx.items if hasattr(i, "text_content")]
    assert not any("Hoy es" in t for t in texts2), "the note is written once per session"
