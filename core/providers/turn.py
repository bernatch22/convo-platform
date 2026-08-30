"""Turn taking: Silero VAD and the local turn detector, both on CPU, no downloads.

`inference.VAD` is a native binary (livekit-local-inference) and
`inference.TurnDetector()` is the v1-mini audio model that ships with the
SDK and runs locally when no LiveKit Cloud inference is configured
(`local_fallback=True`). `min_silence_duration` stays at 0.25 s: below it
the session refuses to start.
"""

from livekit.agents import inference

MIN_SILENCE_S = 0.25


def vad_for():
    """Silero, 250 ms of silence before a segment closes — the floor the session accepts."""
    return inference.VAD(model="silero", min_silence_duration=MIN_SILENCE_S)


def turn_detector_for():
    """The local v1-mini end-of-turn model; Spanish is calibrated in the SDK."""
    return inference.TurnDetector(local_fallback=True)
