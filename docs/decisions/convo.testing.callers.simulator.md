# `convo.testing.callers.simulator`

The reasoning that used to live in the docstrings of `convo/testing/callers/simulator.py`; the code keeps one line per symbol.

## module

A golden is a sentence somebody wrote down because they thought of it. The one that
breaks "never write before a yes" is the conversation nobody thought of — the caller
who changes their mind twice, or backs out the moment the amount is read to them.
`ConversationSimulator` writes the caller's next line from a persona and the
transcript so far; everything on the other side of the line is the real thing, the
same `AgentSession`, tools, guard and saga a phone call gets.

Three decisions, made once here so no project makes them again: one live session
per conversation (`live_conversation`), because replaying re-generates the replies
the caller was answering; a deterministic stopping controller, because tool names
already answer "is this settled?" and DeepEval's default pays a judge per turn to
ask it; and one conversation at a time, because it keeps the calls in golden order
— which is how they are paired back up — and N sessions at once buys nothing.

What a project supplies is what it owns, and nothing else: personas and goldens, a
context already sitting where the stage begins, the stage class, and the tool names
that settle a call. Naming those four things is the whole of a tenant's simulator.

## settled_when

`endings` maps a tool name to why the call is over: both the write that
settles it and the refusal that settles it the other way. A conversation
that ends neither way runs to `max_user_turns` and is scored as it stands.

## SimulatedCaller

DeepEval hands a callback one user line at a time and expects the assistant's
answer back, with no notion of a session behind it. The `thread_id` it passes
is the only thing that says which conversation a line belongs to, so it keys
the open calls — and the goldens are handed out in order as those calls open,
which is how a project gives each conversation its own customer.
