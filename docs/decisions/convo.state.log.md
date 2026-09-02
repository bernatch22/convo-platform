# `convo.state.log`

The reasoning that used to live in the docstrings of `convo/state/log.py`; the code keeps one line per symbol.

## module

Every fact worth auditing — a stage entered, a tool called, a yes granted, a
saga undone, a turn with its latencies — becomes one Event with the next
`seq` and a millisecond offset from the session start, and reaches the store
BEFORE `append` returns. There is no buffer to lose: a process killed mid-call
leaves a log that ends exactly where the call did (call log v3 contract:
live ≡ stored, append-only, never edited).

Kinds are plain dotted strings so a reader needs no enum to grep a log:
  session.start · session.end            the envelope (outcome, cost)
  stage.enter · stage.handoff             the process moving on
  tool.call · tool.result · tool.error · tool.refused   masked args, never payloads —
                                        `tool.result` may carry the one-line `summary` its
                                        ToolSpec's `result_summary` rendered, masked like
                                        everything else that passes through `record`
  confirm.request · confirm.granted · confirm.declined  the caller's yes or no
  saga.fail · saga.compensated            what was undone, last first
  turn.user · turn.agent                  text + metrics (ttft, e2e) from the framework
  stt.final · state · tts.word            the audio path (ms-6)
  stt.phantom                             a transcript refused: no audio behind it
  audio.start                             sample 0 of the recording, in log time
  supervisor.join · supervisor.steer      a second human on the line: hidden, then whispering
  supervisor.takeover · supervisor.release   the line changing hands, and coming back
  supervisor.transfer                     the call handed on to somebody else

A supervisor's verbs are appended to the CALLER's log, not a log of their own:
one call is one story, and "at seq 41 a human took the line" only means
anything in the same sequence as the turn before it. The names live in
`core.security.supervisor` so a handler imports them instead of retyping them.

Open source note: framework-agnostic; `Store` is a Protocol, `MemoryStore`
and `SQLiteStore` ship with it, Postgres is one more file.

## record

A stage, a confirmation and a saga all run in tests and in the console with
a context that was never given a log, and none of them should carry an
`if` about it. This is that `if`, written once.

It is also the one place their payloads are scrubbed: none of them has a
`ToolSpec` to mask by name, and a confirmation question or a saga cause is
free text that can easily repeat the caller's name. Everything the session
already knows to be PII (`tc.pii_values`) is blanked here.
