# `convo.providers.turn`

The reasoning that used to live in the docstrings of `convo/providers/turn.py`; the code keeps one line per symbol.

## module

`inference.VAD` is a native binary (livekit-local-inference) and
`inference.TurnDetector()` is the v1-mini audio model that ships with the
SDK and runs locally when no LiveKit Cloud inference is configured
(`local_fallback=True`). `min_silence_duration` stays at 0.25 s: below it
the session refuses to start.
