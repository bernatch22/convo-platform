# `convo`

The reasoning that used to live in the docstrings of `convo/__init__.py`; the code keeps one line per symbol.

## module

Named `convo`, not `platform`, on purpose: a top-level package called
`platform` shadows the standard-library module of that name, which anthropic,
httpx and pytest import — the whole test suite would break the day the folder
appeared. `python -m convo sessions list|show <id>`.
