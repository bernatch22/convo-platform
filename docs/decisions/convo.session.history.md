# `convo.session.history`

The reasoning that used to live in the docstrings of `convo/session/history.py`; the code keeps one line per symbol.

## module

Anthropic refuses a whole request when the history it is handed contains a
`tool_use` block with no matching `tool_result` (or a result with no call)
with a 400. On a live call that is not a degraded answer, it is the end of the
conversation: every subsequent turn carries the same broken history and fails
the same way. The pairing is therefore an invariant of anything we hand to
`Agent.update_chat_ctx`, and this module is where it is enforced.

Why it exists at all, given `core.providers.llm` says the framework already
does this: the framework's `group_tool_calls` runs at REQUEST time, on a copy,
one layer below us. It saves the request; it does not save the history. What a
supervisor's whisper does is different in kind — it takes the agent's context,
adds a message and writes the result BACK with `update_chat_ctx`, so a context
that was mid-tool-call when the whisper landed becomes the agent's permanent
history. `sanitize_tool_pairing` is what keeps that write clean; the framework
still cleans every request afterwards, and the two do not fight.

The rule is deliberately blunt: an item that is one half of a pair whose other
half is absent is dropped, everything else is kept in order. A dropped
unanswered call is a tool the model asked for and never heard back about,
which is exactly what a mid-flight interruption leaves behind.

Open source note: framework-agnostic apart from the `ChatContext` type — the
same twelve lines work for any history that models tool calls as two items
joined by a `call_id`.

## sanitize_tool_pairing

A new `ChatContext` is returned and the one passed in is untouched, so a
caller can compare the two to see what a swap cost.
