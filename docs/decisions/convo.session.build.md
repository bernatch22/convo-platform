# `convo.session.build`

The reasoning that used to live in the docstrings of `convo/session/build.py`; the code keeps one line per symbol.

## module

Two shapes of session leave this module. A voice session listens and speaks:
the STT's own endpointing and the local turn detector share the decision of
when the caller has finished, a real interruption needs two words so a "vale" does not
cut the agent off, and every spoken word comes back with its time for the log.
A text session has none of it, and audio is switched off so the console's
default audio mode does not crash.

Which one you get is decided by the SESSION's channel first and the keys
second. A chat session never asks for STT or TTS even when both keys are in
the environment: `stt_for` opens a transcription websocket the typed conversation
would never feed, and a provider nobody speaks to is a connection, a cost and
a leak of the caller's audio permissions for nothing.

## build_session

The channel gates the audio providers: on `chat` no STT, no TTS and no VAD
are built at all, so a typed session opens zero provider connections even
with every key present. On `voice` the keys decide, as they always did.

The observers are wired here and nowhere else. They have to be subscribed
before the session starts — the entry agent's `on_enter` runs inside
`session.start`, so a handler attached afterwards misses the greeting that
opened the call — and building the session is the one moment every caller
(worker, console, harness) passes through.

## channel_options

Text input (`lk.chat`) and the agent's transcription (`lk.transcription`)
are on in both — a voice caller still reads what was said.

## start_session

`record=True` asks the framework for the stereo OGG (caller on one channel,
agent on the other) that ms-6's offline evals score. It is passed
explicitly because the default is the SERVER's setting
(`job.enable_recording`), which a laptop console has no server to ask.

`channel` is the session's, never the project's: the same project answers a
phone call with audio tracks and a web chat with text, and only the room IO
differs. It is passed to `session.start` because a room the agent joins
with audio enabled publishes a track and subscribes to one — on a chat
session that is a microphone permission nobody asked for.
