# `convo.testing.callers.stt_script`

The reasoning that used to live in the docstrings of `convo/testing/callers/stt_script.py`; the code keeps one line per symbol.

## module

The voice ring needs one thing no live provider will give it on demand: an STT
that hallucinates. `ScriptedSTT` emits the finals it was handed on a stopwatch
and never looks at the audio, so a test can reproduce the exact shape of the
human's call AJ_rt86KogpPxDa — comfort noise on the line and a confident
`"Thank you."` out of it — deterministically, offline and for free.

`ScriptedMicrophone` is the other half: an `AudioInput` that plays a fixed line
of frames into the session and then holds the line open, the way a silent
caller does. `comfort_noise` and `speech` build those frames at a level, which
is the only property `core.stt_gate` reads.

Together they exercise the whole audio path the framework really runs —
`AgentSession` → `AudioRecognition` → `Agent.stt_node` → the gate — without a
key, a room or a second of billed audio.

Open source note: nothing here knows about tenants. Hand `ScriptedSTT` to any
`AgentSession` and it will hear what you wrote down.
