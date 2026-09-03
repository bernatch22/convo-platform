# `convo.testing.harness`

The reasoning that used to live in the docstrings of `convo/testing/harness.py`; the code keeps one line per symbol.

## module

`session.run()` is what the console uses; here it runs headless so a test can
assert on the exact events (messages, tool calls, handoffs) and DeepEval can
score the text. Nothing here needs a LiveKit server.

Two ways in, one machine underneath. `run_conversation` plays a script that was
written before the call — the ms-2 and ms-3 goldens. `live_conversation` holds
the same session open and lets the caller decide the next line after hearing the
last one, which is what a simulated patient (ms-3 evals) does.

Since ms-6 it has a third mode. `live_conversation(..., record=path)` still
types the caller's lines, but the agent's are SPOKEN by the project's TTS into
the stereo OGG the framework writes for a real call — the file the offline
voice metrics score. The audio machinery lives in `convo.testing.callers.speaker`; this
module only decides when to switch it on.

## model_under_test

A name the platform will not run RAISES here, and does not fall back the way
`convo.providers.llm.llm_model` does for a running call. The fallback is right
on the phone — a typo in a stored override must not take a project off the
air — and wrong in an eval, where it would quietly measure Haiku, write
`gpt-5.4-mini` at the top of the report and leave nobody any the wiser.

## fake_context

`today` is fixed so a test can name the date it expects ("el jueves" is
2026-09-03) without the assertion rotting overnight; wired with the tenant's
adapters and a local executor exactly as `convo.session.router.resolve` wires one.

`llm_model` (or `$CONVO_EVAL_MODEL`) puts the run on another allowed model.
It travels as project data through the same field a console override writes,
so the eval measures the road a real call takes and not a second wiring of
its own — and it is set on a COPY, because the registry hands out one
`Project` instance per process and a suite must not leave the next test on a
model it never asked for.

## PlatformCall

The other half of the story a `RunResult` tells. `book_appointment` is a
tool the MODEL calls, and it calls it before the caller has agreed to
anything — reading the hour back and waiting for a yes is what it does. The
write that needs consent is `book_slot`, which the platform runs itself
once `ConfirmTask` has minted a token, and no event in the run says when
that happened. An eval that judges "nothing was booked before the yes" off
the model's calls alone is judging the wrong event.

## LiveCall.next_line

`after` is `len(call.lines_said())` from before whatever triggered it: a
supervisor's `inject_and_speak`, a release, a timeout prompt. Those lines
never come back through `say`, because there is no turn to attach them
to. Empty string when the agent stayed silent for `timeout` seconds,
which is an answer too — the assertion belongs to the test.

## RecordingExecutor

A decorator, not a fork: it delegates to the real executor, so the guard,
the timeouts and the spoken failure sentences all still apply and what it
records is what actually happened. Only the harness installs it.

## live_conversation

For anything that writes the next user line only after hearing the last
one. Replaying the script from scratch on every turn would cost n(n+1)/2
turns instead of n and — worse — re-generate the replies that line was
answering, so the transcript scored afterwards is one nobody ever had.

`record=<path>` speaks the replies through the project's TTS into the
stereo OGG the framework writes for a real call, with the caller's channel
silent because the caller typed. `audio.start` is appended at the moment
sample 0 is written, so every later `t_ms` in the log is also an offset
into that file — see `convo.testing.callers.audio`.

## run_conversation

The greeting comes from `on_enter` before any user input, exactly as on a
real call; goldens that judge the opening line read `Conversation.greeting`.

`agent` defaults to the project's entry agent, which is what a real call
starts with. A test passes a later stage when what it is pinning belongs to
that stage and driving the conversation there through the model would only
add turns, cost and variance to an assertion about something else.

## final_message

One turn can hold several: Haiku often says "un momento, le consulto la
agenda" before calling a tool and only answers once the result is back.
Judging the first message would be judging the filler, so a golden about
what the agent ANSWERS reads this one; a golden about the order of events
(a tool call before the answer) still walks `result.expect` itself.
