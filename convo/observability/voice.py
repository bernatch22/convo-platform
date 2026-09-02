"""observe_voice: the audio path's own events, on top of what `observe` already records.

Decisions: docs/decisions/convo.observability.voice.md
"""

import logging
from typing import Any

log = logging.getLogger("platform.voice")

# Words held before one `tts.word` event is written. ElevenLabs streams the
# alignment for a sentence faster than the sentence is spoken, so one append
# per word is a burst of ~12 synchronous store writes inside the audio path.
# A sentence is also the unit an operator reads a transcript in.
MAX_WORDS_PER_EVENT = 12
SENTENCE_END = ".!?…\n"


def observe_voice(session, tc) -> None:
    """Wire one voice session's interruption events into `tc.log`; no log, no work."""
    if getattr(tc, "log", None) is None:
        return
    observer = VoiceObserver(tc)
    for event, handler in observer.handlers().items():
        session.on(event, handler)


def recording_path(session) -> str | None:
    """The OGG the session is recording into, or None when `record=` was off."""
    recorder = getattr(session, "_recorder_io", None)
    path = getattr(recorder, "output_path", None)
    return str(path) if path else None


class VoiceObserver:
    """Holds the context so each handler is one line of translation, like `SessionObserver`."""

    def __init__(self, tc) -> None:
        self.tc = tc

    def handlers(self) -> dict[str, Any]:
        """The framework's audio-path event names mapped to the methods that record them."""
        return {
            "agent_false_interruption": self.on_false_interruption,
            "overlapping_speech": self.on_overlapping_speech,
        }

    def on_false_interruption(self, event) -> None:
        """The barge-in meant nothing; `resumed` is whether the sentence came back."""
        self.tc.log.append("interruption.false", {"resumed": bool(event.resumed)})

    def on_overlapping_speech(self, event) -> None:
        """Both spoke at once: the detector's verdict, its confidence and how late it was."""
        self.tc.log.append(
            "speech.overlap",
            {
                "interruption": bool(event.is_interruption),
                "agent_ended": bool(event.agent_ended),
                "probability": round(float(event.probability), 3),
                "delay": round(float(event.detection_delay), 3),
            },
        )


class TimedWords:
    """Buffers the agent's timed words and writes one `tts.word` event per sentence."""

    def __init__(self, tc) -> None:
        self.tc = tc
        self.words: list[dict[str, Any]] = []

    def add(self, delta: str) -> None:
        """Take one transcription delta; write the sentence out when it ends."""
        text = delta.strip()
        if not text:
            return
        end_time = getattr(delta, "end_time", None)
        if isinstance(end_time, (int, float)):
            self.words.append({"w": text, "t1": round(float(end_time), 3)})
        if delta.rstrip()[-1:] in SENTENCE_END or len(self.words) >= MAX_WORDS_PER_EVENT:
            self.flush()

    def flush(self) -> None:
        """Write what is buffered, if anything; called again at the end of the stream."""
        if not self.words or getattr(self.tc, "log", None) is None:
            self.words = []
            return
        self.tc.log.append("tts.word", {"words": self.words})
        self.words = []
