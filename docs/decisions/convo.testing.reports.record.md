# `convo.testing.reports.record`

The reasoning that used to live in the docstrings of `convo/testing/reports/record.py`; the code keeps one line per symbol.

## module

    uv run python -m convo.testing.reports.record clinica-norte reagendamiento

The caller's lines are typed (the list below); the agent's are synthesised by
the project's real ElevenLabs voice and played, in real time, into the stereo
OGG the framework writes for a `--record` call. What comes out is a session in
`tmp/convo.db` and an `audio.ogg` next to it — exactly the two things
`python -m convo sessions show|eval <id> --voice` reads.

Why not a real console call: Soniox bills per second of audio and the
offline voice metrics never look at the caller's channel, so sending it
anything would be paying for silence. The key is dropped from the environment
here so the session cannot open a Soniox stream by accident, which also means
**no `stt.final` events in this log**. The trade is written down in
`docs/evals.md` §3.9; `convo console --record` is the run that has
them, and it needs a human with a microphone.
