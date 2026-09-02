# `convo.providers.tts`

The reasoning that used to live in the docstrings of `convo/providers/tts.py`; the code keeps one line per symbol.

## module

The voice is project data (`Project.voice`), never a constant here: two
projects of one tenant can sound like two people. `eleven_v3_conversational`
is the realtime member of the v3 family; `eleven_v3` itself is not realtime
and `eleven_turbo_v2_5` is deprecated, so neither is ever chosen even when a
project asks. `eleven_flash_v2_5` is the latency profile a project may opt
into. `sync_alignment=True` gives the session timed words for the event log.

## tts_for

`voice` overrides the project's for one stage that has its own
(`Project.stage_voices`) — the model, the language and the alignment stay
the project's, because a second desk is another person at the same business
and not another business.
