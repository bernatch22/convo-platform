# `convo.prompting.layout`

The reasoning that used to live in the docstrings of `convo/prompting/layout.py`; the code keeps one line per symbol.

## module

The order is measured, not aesthetic (docs/decisions/002-prompt-layout.md): the
knowledge block is the cached prefix, and the supervisor protocol is last because
the final paragraph is the one that outranks the stage script.
