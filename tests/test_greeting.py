"""The greeting is a line, not an LLM turn: spoken at once, once, and only at the door."""

import pytest

from core.testing import fake_context

pytestmark = pytest.mark.unit


class SpyingSession:
    def __init__(self):
        self.said, self.generated = [], 0

    def say(self, text, **kw):
        self.said.append(text)

    def generate_reply(self, **kw):
        self.generated += 1


async def test_the_entry_stage_speaks_the_greeting_without_an_llm_turn(monkeypatch) -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    stage = tc.project.entry_agent(tc)
    spy = SpyingSession()
    monkeypatch.setattr(type(stage), "session", property(lambda self: spy))

    await stage.on_enter()

    assert spy.said == [tc.project.greeting] and spy.generated == 0


async def test_a_handoff_stage_still_opens_with_the_model(monkeypatch) -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    first, second = tc.project.stages(tc)[0], tc.project.stages(tc)[1]
    spy = SpyingSession()
    monkeypatch.setattr(type(second), "session", property(lambda self: spy))

    tc.prev_agent = first  # the session already started somewhere
    await second.on_enter()

    assert spy.said == [] and spy.generated == 1
