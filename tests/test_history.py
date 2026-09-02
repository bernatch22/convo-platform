"""Half a tool exchange is a 400 that ends the call: the history never keeps one.

Anthropic refuses the whole request when a `tool_use` has no `tool_result`, and
because the history is carried forward every later turn fails the same way. So
the invariant is not "the request was clean" but "what we WROTE BACK was
clean" — which is what `sanitize_tool_pairing` guards, and what makes it safe
for a supervisor's whisper to swap the agent's context at any moment.
"""

import pytest
from livekit.agents.llm import ChatContext, FunctionCall, FunctionCallOutput

from convo.session.history import orphans, sanitize_tool_pairing

pytestmark = pytest.mark.unit


def test_a_complete_tool_exchange_survives_untouched() -> None:
    chat_ctx = _ctx(_call("c1"), _output("c1"))

    assert [item.type for item in sanitize_tool_pairing(chat_ctx).items] == [
        "function_call",
        "function_call_output",
    ]


def test_a_call_nobody_answered_is_dropped() -> None:
    """What an interruption mid-tool-call leaves behind, and what would 400 on the next turn."""
    chat_ctx = _ctx(_call("c1"))
    chat_ctx.add_message(role="user", content="¿sigues ahí?")

    kept = sanitize_tool_pairing(chat_ctx)

    assert [item.type for item in kept.items] == ["message"]


def test_an_answer_to_a_call_that_is_not_there_is_dropped() -> None:
    assert sanitize_tool_pairing(_ctx(_output("gone"))).items == []


def test_messages_keep_their_order_around_the_hole() -> None:
    chat_ctx = ChatContext()
    chat_ctx.add_message(role="user", content="quiero cambiar la cita")
    chat_ctx.insert(_call("c1"))
    chat_ctx.add_message(role="assistant", content="un momento")

    kept = [item.text_content for item in sanitize_tool_pairing(chat_ctx).items]

    assert kept == ["quiero cambiar la cita", "un momento"]


def test_the_context_handed_in_is_never_mutated() -> None:
    """A caller has to be able to compare before and after to see what a swap cost."""
    chat_ctx = _ctx(_call("c1"))

    sanitize_tool_pairing(chat_ctx)

    assert [item.type for item in chat_ctx.items] == ["function_call"]


def test_orphans_names_the_call_ids_that_would_have_400ed() -> None:
    assert orphans(_ctx(_call("c1"), _output("c1"), _call("c2"))) == ["c2"]
    assert orphans(_ctx(_call("c1"), _output("c1"))) == []


def _ctx(*items) -> ChatContext:
    chat_ctx = ChatContext()
    for item in items:
        chat_ctx.insert(item)
    return chat_ctx


def _call(call_id: str) -> FunctionCall:
    return FunctionCall(call_id=call_id, name="check_slots", arguments="{}")


def _output(call_id: str) -> FunctionCallOutput:
    return FunctionCallOutput(call_id=call_id, name="check_slots", output="[]", is_error=False)
