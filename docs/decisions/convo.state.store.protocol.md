# `convo.state.store.protocol`

The reasoning that used to live in the docstrings of `convo/state/store/protocol.py`; the code keeps one line per symbol.

## PipelineOverride

Voice, TTS model and greeting are the three a supervisor changes between
calls; the row is what makes the change survive without a deploy. The read
is one row per field, so the console can show when each was last touched.

## EvalRun

Stored the moment it starts (`status="running"`) so the console can watch it
land, then replaced by id when it ends. `suite` is free text on purpose —
ring 1 today, personas tomorrow — and nothing here knows which is which.
