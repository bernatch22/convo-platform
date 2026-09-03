# `convo.testing.replay.tools`

The reasoning that used to live in the docstrings of `convo/testing/replay/tools.py`; the code keeps one line per symbol.

## module

Two events make one call. `tool.call` opens it with the masked arguments the
executor wrote; `tool.result` or `tool.error` closes it with what came back —
and since ms-7 "what came back" is a real sentence whenever the tool's
`ToolSpec` declared a `result_summary`, instead of the shape and an apology.

That summary is the whole reason a replayed call can be scored for grounding.
`convo.testing.metrics.grounding.evidence_of` reads `ToolCall.output`, so an hour the
agenda offered is evidence the moment the agenda's summary is in the log, and a
metric that used to score every real session 0.0 on its own blindness now
scores what the agent actually did.

Tools that declare no renderer still come through as `NO_PAYLOAD`, and
`missing_tool_outputs` still names them: a project opts in tool by tool, and
the CLI has to keep saying which of them a reader must not read a 0.0 from.

## missing_tool_outputs

Anything a caller states that came from one of these has no evidence behind
it in a replayed case — not because the agent invented it, but because the
tool declared no `result_summary` and the log kept only a shape. A CLI or a
report says this next to the score; an empty list means the call is as
groundable as it was live.

## Calls._close

Oldest first because the executor awaits one call at a time per chain,
and there is no call id in the log to pair on — the name and the order
are all a reader of the log has, so they are all this uses.
