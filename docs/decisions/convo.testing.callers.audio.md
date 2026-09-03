# `convo.testing.callers.audio`

The reasoning that used to live in the docstrings of `convo/testing/callers/audio.py`; the code keeps one line per symbol.

## module

Two callers, one vocabulary. Ring 3 (`voice_case_from`) reads the stereo OGG a
finished call left behind; ring 2 (`convo.testing.reports.ring2`) has no file at all —
it holds a live track and builds a `Timeline` as the frames arrive. Both end
at `audio_clip`, which is the only place in the codebase that decides what an
`Audio` on a turn looks like, `start_time` included.

The ring-3 half, in full:

`convo.testing.replay` rebuilds what was SAID from the append-only log. This
adds what was HEARD: the stereo OGG a `--record` call leaves behind, cut into
one clip per agent turn and hung on the turns the replay already built, so
DeepEval's `AudioIntegrityMetric` and `AgentResponsivenessMetric` have
something to measure.

Three facts make the cut possible, and all three are in the log:

  `audio.start`   its `t_ms` is the log time of sample 0 of the OGG — the one
                  number that ties the two clocks together
  `state`         `to: speaking` is the millisecond the agent took the floor
  `turn.agent`    written when the item is committed, i.e. once its audio has
                  played out — so it is the END of the window, not the start

What is deliberately NOT used: `tts.word`'s `t1`. ElevenLabs sends alignment
relative to each websocket chunk and the framework never rebases it, so `t1`
is a word's place inside its own chunk and cannot address the file. See
`convo.observability.voice.TimedWords`.

The caller's channel (L) is whatever the microphone put there — silence on an
offline run, where the caller typed. User turns therefore get no `Audio` at
all rather than a clip of silence that would read as a broken microphone.

Open source note: PyAV decodes both OGG/Opus and WAV, and PyAV is already a
livekit-agents dependency, so this adds nothing to install. Nothing below
knows about tenants or about LiveKit.

## voice_case_from

The turns, the tool calls and the scenario are `replay`'s; this only adds
the agent's audio. `ogg_path` defaults to the file the session log itself
names, so a caller with a session id needs nothing else.

## agent_windows

The agent's audio does not start when its turn is written — the turn is
written when the audio has finished. The last `state → speaking` before the
commit is where the sound begins; a turn with no speaking state before it
(a text-only reply, or one the caller cut off before a word came out) is
reported as an empty window and simply carries no audio.

## split_channels

Every frame goes through one resampler to planar 16-bit stereo, so the OGG
the recorder writes (Opus, float planar) and the synthetic WAVs the unit
test builds (packed integer) arrive at the cutting below in one shape.
PyAV 18's `to_ndarray` takes no format argument — the resampler is the
conversion.

## audio_clip

`start_time` is where this clip begins inside the conversation, in seconds.
It is not decoration: `TurnTakingNaturalnessMetric` rebuilds the call's
timeline from it (`metrics/voice/turn_taking.py:18-23`) and scores nothing
without it, so every turn that carries audio carries an offset too.

## Timeline

An OGG is one continuous file, so `cut` addresses it by offset. A track on
the wire is not: it carries frames only while somebody speaks, and the
silence between two answers is nothing anybody sent. Writing each frame at
its arrival offset rebuilds the missing silence, and a clip cut by two wall
times then lines up with what the room's own events say happened.

Open source note: this is the receiving half of any headless LiveKit
client that wants per-turn audio; it knows nothing about this platform.
