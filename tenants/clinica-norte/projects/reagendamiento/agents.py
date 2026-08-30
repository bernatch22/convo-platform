"""Stages of the reagendamiento conversation. ms-2: a single Reception stage, with one tool."""

from core.agents import TenantAgent
from core.context import TenantContext

from . import knowledge, prompts
from .tools import find_availability


class Reception(TenantAgent):
    """Greets, identifies the clinic, and reads the agenda to offer real hours."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(
            tc,
            instructions=prompts.reception_prompt(knowledge.CLINIC),
            tools=[find_availability],
        )
