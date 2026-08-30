"""Agent base classes and the tool surface a project builds on.

Everything a project needs from the agent framework passes through this package:
projects import `TenantAgent`, `function_tool`, `RunContext` and `ToolError`
from here and never from `livekit.agents`, so swapping the runtime is a change
to `core/`, not to every tenant.
"""

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from core.agents.base import TenantAgent

__all__ = ["RunContext", "TenantAgent", "ToolError", "function_tool"]
