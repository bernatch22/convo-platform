# `convo.api.pipeline`

The reasoning that used to live in the docstrings of `convo/api/pipeline.py`; the code keeps one line per symbol.

## PipelineUpdate

`extra="forbid"`: a typo like `ttsModel` must come back as a 422 naming the
field, not be stored as an override nothing will ever read.
