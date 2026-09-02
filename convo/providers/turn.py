"""Turn taking: Silero VAD and the local turn detector, both on CPU, no downloads.

Decisions: docs/decisions/convo.providers.turn.md
"""

from livekit.agents import inference

MIN_SILENCE_S = 0.25


def vad_for():
    """Silero, 250 ms of silence before a segment closes — the floor the session accepts."""
    return inference.VAD(model="silero", min_silence_duration=MIN_SILENCE_S)


def turn_detector_for():
    """The local v1-mini end-of-turn model; Spanish is calibrated in the SDK."""
    return inference.TurnDetector(local_fallback=True)
