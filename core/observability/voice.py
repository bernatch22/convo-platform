"""observe_voice: the audio path's own events, on top of what `observe` already records.

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
    """The OGG the session is recording into, or None when `record=` was off.

    Read off the recorder rather than off `JobContext.make_session_report()`,
    which is the public door but cannot be opened until the session is closed —
    by which time `session.end` is already written and the log never edits.
    `output_path` is the same field the report copies into
    `SessionReport.audio_recording_path`.
    """
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
        """The barge-in meant nothing; `resumed` is whether the sentence came back.

        `AgentFalseInterruptionEvent.message` and `.extra_instructions` are
        deprecated in 1.7.1 and log a warning on every attribute READ, so this
        handler never touches them.
        """
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
    """Buffers the agent's timed words and writes one `tts.word` event per sentence.

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
    """

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
