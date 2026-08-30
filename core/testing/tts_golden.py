"""The TTS golden: one sentence with a DNI, an amount and a time, on both ElevenLabs models.

    uv run python -m core.testing.tts_golden

`eleven_v3_conversational` is what a project speaks with, `eleven_flash_v2_5`
the latency profile one may opt into. The sentence is what goes wrong in
Spanish contact centres: a document number, a price with a decimal comma, an
hour with a colon.

The measurement it can make on its own, and the one it cannot. TTFB and audio
duration are exact. The aligned transcript is not evidence: in
`livekit-plugins-elevenlabs` 1.7.1 it is ElevenLabs' `normalizedAlignment`, and
for Spanish that comes back with the digits UNCHANGED — the input text, so it
cannot say how a number was SPOKEN. `CONTROL` is what says it: the same
sentence with the three tokens already written out in words. A model that
expands them itself takes about as long as the control; one that swallows them
is seconds shorter. That ratio is deterministic and free. The two WAVs are
written for the human, who has the last word.

Open source note: this needs an ElevenLabs key and nothing else of ours.
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from core.testing.audio import wav_bytes

GOLDEN = (
    "Su DNI 12345678Z queda registrado, el importe es de 74,90 euros "
    "y le esperamos el jueves a las 11:30."
)
# The same sentence with the three tokens already written out as they must be
# read. Its duration is the yardstick: a model that expands the digits itself
# takes about as long as this, and one that swallows them is seconds shorter.
CONTROL = (
    "Su DNI uno dos tres cuatro cinco seis siete ocho zeta queda registrado, el importe es "
    "de setenta y cuatro con noventa euros y le esperamos el jueves a las once y media."
)
TOKENS = ("12345678Z", "74,90", "11:30")
MODELS = ("eleven_v3_conversational", "eleven_flash_v2_5")
VOICE = "UOIqAnmS11Reiei1Ytkc"  # Carolina — es_ES, the platform default
OUT = Path("tmp/golden")


@dataclass
class Synthesis:
    """One sentence spoken by one model: how fast it started, how long it ran, what it aligned."""

    model: str
    ttfb_s: float
    duration_s: float
    transcript: str
    spans: dict[str, float | None] = field(default_factory=dict)
    wav: bytes = b""

    def line(self) -> str:
        """One row of the golden table."""
        spans = "  ".join(f"{token}={_seconds(self.spans.get(token))}" for token in TOKENS)
        return f"{self.model:<26} ttfb {self.ttfb_s:.3f}s  audio {self.duration_s:.2f}s  {spans}"


def read_out(golden: Synthesis, control: Synthesis) -> float:
    """How much of the spelled-out reading the model actually spoke, as a ratio of durations.

    Near 1.0 the model expanded `12345678Z`, `74,90` and `11:30` itself; well
    under it, it did not — and that IS the golden, since the alignment repeats
    the input text and cannot say. It is a duration, so it is exact and free.
    """
    return golden.duration_s / control.duration_s if control.duration_s else 0.0


async def synthesize(model: str, text: str = GOLDEN) -> Synthesis:
    """Speak the sentence once with one model and measure it."""
    from livekit.agents.tts.tts import USERDATA_TIMED_TRANSCRIPT
    from livekit.agents.utils import http_context
    from livekit.plugins import elevenlabs

    from core.providers.tts import KEY_ENV

    async with http_context.open():
        tts = elevenlabs.TTS(
            api_key=os.environ[KEY_ENV],
            voice_id=VOICE,
            model=model,
            language="es",
            sync_alignment=True,
        )
        stream = tts.stream()
        started, first, frames, timed = time.monotonic(), None, [], []
        stream.push_text(text)
        stream.end_input()
        async for event in stream:
            if first is None:
                first = time.monotonic()
            frames.append(event.frame)
            # the aligned words ride on the FRAME, not on `delta_text`, which the
            # ElevenLabs plugin never fills: `AudioEmitter` hangs them off
            # `frame.userdata[USERDATA_TIMED_TRANSCRIPT]` (tts/tts.py:1103)
            timed.extend(event.frame.userdata.get(USERDATA_TIMED_TRANSCRIPT) or [])
        await stream.aclose()
        await tts.aclose()
    return _measure(model, started, first, frames, timed)


def main(argv: list[str]) -> int:
    """CLI: synthesises the golden on both models, writes the WAVs, prints the numbers."""
    load_dotenv(".env")
    OUT.mkdir(parents=True, exist_ok=True)
    chars = (len(GOLDEN) + len(CONTROL)) * len(MODELS)
    print(f"golden:  {GOLDEN}\ncontrol: {CONTROL}\n({chars} characters billed)\n")
    measured = {}
    for model in MODELS:
        golden = asyncio.run(synthesize(model, GOLDEN))
        control = asyncio.run(synthesize(model, CONTROL))
        (OUT / f"{model}.wav").write_bytes(golden.wav)
        (OUT / f"{model}-control.wav").write_bytes(control.wav)
        print(golden.line())
        print(
            f"  spelled-out control {control.duration_s:.2f}s"
            f" — read {read_out(golden, control):.0%} of it"
        )
        print(f"  aligned transcript: {golden.transcript}")
        print(f"  wav: {OUT / f'{model}.wav'}\n")
        measured[model] = {
            "ttfb_s": round(golden.ttfb_s, 3),
            "audio_s": round(golden.duration_s, 2),
            "control_s": round(control.duration_s, 2),
            "read_out": round(read_out(golden, control), 3),
            "spans": golden.spans,
            "transcript": golden.transcript.strip(),
        }
    # the report reads this rather than re-synthesising: ElevenLabs bills per character
    (OUT / "golden.json").write_text(json.dumps({"golden": GOLDEN, "models": measured}, indent=2))
    return 0


def _measure(model, started, first, frames, timed) -> Synthesis:
    """Turn the raw stream into the row above: TTFB, duration, transcript, per-token spans."""
    rate = frames[0].sample_rate if frames else 48000
    pcm = b"".join(bytes(frame.data) for frame in frames)
    return Synthesis(
        model=model,
        ttfb_s=(first or started) - started,
        duration_s=sum(frame.duration for frame in frames),
        transcript="".join(str(delta) for delta in timed),
        spans=_spans(timed),
        wav=_wav(pcm, rate),
    )


def _spans(timed) -> dict[str, float | None]:
    """Seconds the alignment gives each golden token, or None where it cannot be read.

    `end_time` is relative to the websocket chunk the word arrived in (see
    `core.observability.voice.TimedWords`), so a word's span is the step up
    from the word before it — and a word that opens a new chunk has no
    measurable step. That is reported as None rather than as the small positive
    number the reset would otherwise produce.
    """
    spans: dict[str, float | None] = {}
    previous = 0.0
    for delta in timed:
        end = float(delta.end_time)
        step = end - previous if end >= previous else None
        previous = end
        for token in TOKENS:
            if token in str(delta) and token not in spans:
                spans[token] = step
    return spans


def _seconds(value: float | None) -> str:
    """A span, or `?` for one that straddled a chunk boundary and cannot be read."""
    return f"{value:.2f}s" if value is not None else "?"


def _wav(pcm: bytes, rate: int) -> bytes:
    """The synthesised audio as a 16-bit mono WAV a browser can play."""
    import numpy as np

    return wav_bytes(np.frombuffer(pcm, dtype=np.int16), rate)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
