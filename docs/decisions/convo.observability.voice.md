# `convo.observability.voice`

The reasoning that used to live in the docstrings of `convo/observability/voice.py`; the code keeps one line per symbol.

## module

`core.observability.observers` records what every session has — turns, final
transcripts, state, tools, the close. This file records what only a session
with a microphone has: an interruption the framework decided was false, an
overlap the detector judged, and the agent's own words with the times they
were spoken at.

The vocabulary it adds to the log:

  interruption.false   the caller's noise did not mean "stop"; `resumed` says
                       whether the agent picked its sentence back up
  speech.overlap       both talked at once; `interruption` is the verdict
  tts.word             the agent's words with `t1` (end_time), one event per
                       sentence — see `TimedWords` for why not per word, and
                       for what `t1` is and is not

What it deliberately does NOT record: interim transcripts. `observe` already
keeps `stt.final` only, and an audit log full of hypotheses that were revised
half a second later is a log nobody reads.

Open source note: only `tc.log` is needed. Everything else is LiveKit event
names, and they all live in this file and `observers.py`.

## recording_path

Read off the recorder rather than off `JobContext.make_session_report()`,
which is the public door but cannot be opened until the session is closed —
by which time `session.end` is already written and the log never edits.
`output_path` is the same field the report copies into
`SessionReport.audio_recording_path`.

## VoiceObserver.on_false_interruption

`AgentFalseInterruptionEvent.message` and `.extra_instructions` are
deprecated in 1.7.1 and log a warning on every attribute READ, so this
handler never touches them.

## TimedWords

Fed from `TenantAgent.transcription_node`, which forwards every delta on
untouched: this only reads. A delta with no `end_time` (a plain `str`, or a
provider that sent no alignment) is text we cannot place in time, so it is
counted for the flush but never recorded with a time it does not have.

What `t1` is: `TimedString.end_time` exactly as the TTS plugin produced it.
In 1.7.1 the ElevenLabs plugin builds it from `normalizedAlignment`'s
`chars_start_times_ms`, which ElevenLabs sends relative to EACH websocket
message, and the framework never rebases it (`start_time_offset` is set for
STT only, `voice/agent.py:519`). So `t1` is a word's place inside its own
synthesis chunk and is NOT monotonic across a sentence — a real run reads
`Buenos@0.30 días,@0.11 le@0.21`.

What IS on the session timeline is the event's own `t_ms`, which `EventLog`
stamps from the session start. Anything aligning words against the OGG —
ms-6's offline evals — takes the sentence from `t_ms` and uses `t1` only
for the word's duration inside it.
