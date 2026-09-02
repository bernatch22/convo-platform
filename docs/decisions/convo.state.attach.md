# `convo.state.attach`

The reasoning that used to live in the docstrings of `convo/state/attach.py`; the code keeps one line per symbol.

## module

`attach_log` runs when the job starts, `close_log` when it shuts down. Between
them the log is written by the observers and the executor, append by append,
so closing adds no events — only the framework's end-of-call report, which is
the one artefact that does not exist until the call is over.

## attach_log

`sip` is the caller's `sip.*` attributes when the session came in over the
phone: the dialled number, the carrier's call id and the headers the trunk
was told to keep. They belong on the very first event — an audit asks which
number was dialled long before it asks what was said.

`pipeline` is the other half of that: the voice, the two models and the ear
this session really resolved to, AFTER the console's overrides. Without it
a supervisor who changes the voice has no artefact saying which voice the
next call spoke with, and "I picked Carolina and heard someone else" cannot
be answered from the log.

## close_log

The events are already durable — every append reached the store during the
call — so this only writes what exists at the end. A context with no log
has nothing to close.

## outcome_of

A process killed mid-call leaves no close event, and `dropped` is exactly
what that means: the log ends where the call did.
