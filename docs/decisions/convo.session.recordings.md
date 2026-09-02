# `convo.session.recordings`

The reasoning that used to live in the docstrings of `convo/session/recordings.py`; the code keeps one line per symbol.

## module

One module owns the answer, because three very different callers ask it: the
job process (which writes the OGG), the control plane (which serves it) and
the console (which shows a player). None of them should be composing a path.

The capture itself is the framework's — `AgentSession.start(record=True)`
wraps the session's audio IO with a `RecorderIO` whose only cost on the call
path is one `queue.put_nowait` per frame; the Opus encode runs in a daemon
thread and flushes every 2.5 s. What the framework gets wrong for us is the
DESTINATION: outside the console, `JobContext` points the recorder at a
`tempfile.TemporaryDirectory()` and deletes it in `_on_cleanup()`, so a real
call records perfectly and then loses the file on the way out. `aim` is that
one fix — the recorder streams straight into its final home during the call,
so a SIGKILLed job leaves the audio it had, the same discipline the event log
already follows.

Recordings hold PII. They never enter git (`tmp/` and `*.ogg` are ignored,
and the box keeps them under `CONVO_RECORDINGS`), they are read back by
SESSION ID and never by a path taken from a log payload, and `authorised`
is the door's bolt when the deploy sets `RECORDINGS_TOKEN`.

Open source note: framework-agnostic except `aim`, which is four lines of
livekit-agents 1.7.1 and fails closed if the private attribute it sets ever
goes away.

## for_session

None covers every honest reason a call has no audio: it was a chat, its
project opted out, the job died before a flush, or the id is not one we
would ever have written. The caller cannot tell those apart and must not:
all of them mean "there is nothing to play".

## keep

Modelled on `Project.scoring`: it is a business decision (a tenant that has
not agreed to recording, a queue whose calls are two sentences long), so it
lives with the project's data and not in an environment variable.

## aim

`JobContext.session_directory` is a read-only property over a private
attribute and livekit-agents 1.7.1 offers no public setter for it (checked:
`AgentServer`, `WorkerOptions` and `RecordingOptions` all decide WHETHER to
record, never WHERE). Assigning it is therefore the whole of the fix and it
is written down in exactly one place — here — so the day the framework
grows a real setter there is one line to change.

It fails closed on purpose: a context that will not take the attribute
returns None, the caller passes `record=False`, and calls stop being
recorded instead of the fleet falling over.

## authorised

The control plane has no login, so this is not one. It is the bolt a box
that exposes `/sessions/{id}/recording` beyond its own network sets: with
`RECORDINGS_TOKEN` in the environment the route wants exactly that string,
and without it the route is as open as every other read on this API and
the deploy is expected to say so in `infra/box/README.md`.
