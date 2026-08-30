"""Farewell: confirm the cancellation out loud, promise the SMS, and close the call."""

from core.agents import TenantAgent
from core.context import TenantContext

from .. import prompts


class Farewell(TenantAgent):
    """Reads the cancellation back, mentions the refund and the SMS, says goodbye. No tools.

    Deliberately toolless: everything this stage says it already knows from the
    summary OrderDesk left it. A stage that could still touch the order system
    would be a second chance to cancel something after the customer has been
    told the call is over — which is exactly the bug the three-stage split
    exists to prevent.
    """

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=prompts.farewell_prompt(tc))

    def summary(self) -> str:
        """The last stage of the call; nothing downstream reads this, but the shape holds."""
        return "La llamada se ha cerrado tras confirmar la cancelación."
