# `convo.agents`

The reasoning that used to live in the docstrings of `convo/agents/__init__.py`; the code keeps one line per symbol.

## module

Everything a project needs from the agent framework passes through this package:
projects import `TenantAgent`, `function_tool`, `RunContext` and `ToolError`
from here and never from `livekit.agents`, so swapping the runtime is a change
to `convo/`, not to every tenant.
