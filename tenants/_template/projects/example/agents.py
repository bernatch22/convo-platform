"""One TenantAgent per stage."""

from core.agents import TenantAgent
from core.context import TenantContext

from . import prompts


class Welcome(TenantAgent):
    """Greets and asks how to help."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=prompts.WELCOME)
