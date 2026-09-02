# `convo.testing.callers.tts_golden`

The reasoning that used to live in the docstrings of `convo/testing/callers/tts_golden.py`; the code keeps one line per symbol.

## module

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

## read_out

Near 1.0 the model expanded `12345678Z`, `74,90` and `11:30` itself; well
under it, it did not — and that IS the golden, since the alignment repeats
the input text and cannot say. It is a duration, so it is exact and free.

## _spans

`end_time` is relative to the websocket chunk the word arrived in (see
`core.observability.voice.TimedWords`), so a word's span is the step up
from the word before it — and a word that opens a new chunk has no
measurable step. That is reported as None rather than as the small positive
number the reset would otherwise produce.
