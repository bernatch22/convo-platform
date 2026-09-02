# `convo.tools.messages`

The reasoning that used to live in the docstrings of `convo/tools/messages.py`; the code keeps one line per symbol.

## module

A failed tool call is still a turn of the conversation: the model reads the
message and says it, so it must sound like the project. Register is project
data, not platform data — a clinic that addresses patients as "usted" cannot
suddenly say "¿puedo ayudarte?" because a database timed out. Core therefore
ships a neutral default per failure and a project overrides any of them through
`Project.messages`.

Framework-agnostic on purpose: four keys, a dict of defaults and one lookup, so
the executor of any agent runtime can reuse them.
