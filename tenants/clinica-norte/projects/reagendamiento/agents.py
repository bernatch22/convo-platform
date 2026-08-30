"""Stages of the reagendamiento conversation. ms-1: a single Reception stage."""

from core.agents import TenantAgent
from core.context import TenantContext

from . import knowledge, prompts


class Reception(TenantAgent):
    """Greets, identifies the clinic and asks how to help. No tools yet."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=prompts.reception_prompt(knowledge.CLINIC))
