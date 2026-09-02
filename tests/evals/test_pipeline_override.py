"""A greeting stored through the pipeline API is the sentence the next call opens with.

The whole point of the console's control panel: an override is not a note in a
database, it is the platform's behaviour on the very next session — with no
deploy in between. This golden goes store → resolve → session opening, judged
by nobody: the greeting is spoken verbatim by design, so equality is the test.
"""

import pytest

from convo.state.overrides import apply
from convo.state.store import MemoryStore, PipelineOverride
from convo.testing import fake_context

pytestmark = pytest.mark.evals

GREETING = "Clínica Norte, le atiende recepción por la tarde. Dígame."


async def test_the_stored_greeting_is_the_line_the_next_session_opens_with(monkeypatch) -> None:
    store = MemoryStore()
    store.set_pipeline_override(
        PipelineOverride("clinica-norte", "reagendamiento", "greeting", GREETING)
    )

    tc = fake_context("clinica-norte", "reagendamiento")
    tc = tc.__class__(**{**tc.__dict__, "project": apply("clinica-norte", tc.project, store)})
    stage = tc.project.entry_agent(tc)

    said: list[str] = []
    generated: list[bool] = []

    class Spy:
        def say(self, text, **kw):
            said.append(text)

        def generate_reply(self, **kw):
            generated.append(True)

    monkeypatch.setattr(type(stage), "session", property(lambda self: Spy()))
    await stage.on_enter()

    assert said == [GREETING], "the override IS the opening line, verbatim"
    assert not generated, "no LLM turn is spent on a sentence that never changes"
