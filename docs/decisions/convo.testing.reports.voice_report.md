# `convo.testing.reports.voice_report`

The reasoning that used to live in the docstrings of `convo/testing/reports/voice_report.py`; the code keeps one line per symbol.

## module

    uv run python -m convo.testing.reports.voice_report <session-id>

Writes `tmp/reports/ms-6.html` with the OGG playable in the page, one row per
agent turn with the latencies the framework measured, the two offline voice
metrics with their defect breakdown, and the TTS golden read from
`tmp/golden/golden.json` (written by `python -m convo.testing.callers.tts_golden`; it is
read rather than re-run because ElevenLabs bills per character).

Nothing here costs a model call: both voice metrics are DSP.

## turn_rows

`answer_s` is the caller's line to the agent's first sound — the honest
end-to-end of a typed call. It is not the framework's `e2e_latency`, which
needs an end of utterance and so never appears without a microphone; the
greeting, which answers nobody, has none.
