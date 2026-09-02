# `convo.state.overrides`

The reasoning that used to live in the docstrings of `convo/state/overrides.py`; the code keeps one line per symbol.

## module

A supervisor changes a voice, a TTS model or the opening line between two
calls; a deploy is the wrong unit for that. The row lives in the store
(`pipeline_overrides`) and this module is where it becomes a `Project` again:
`resolve` calls `apply` once, so every session — voice, chat, console — starts
from the same overridden object and nothing downstream knows a row was
involved.

Only the fields in `OVERRIDABLE` can be set this way. A value the platform
refuses to run is still refused where it is built: an override naming a
forbidden TTS model is neutralised by `core.providers.tts.tts_model` and one
naming an STT provider we do not have by `core.providers.stt.provider_for`,
and the control plane refuses to store either in the first place.

## apply

Returns the project untouched when there is no row for it, so a deploy with
an empty table behaves exactly as it did before the table existed.
