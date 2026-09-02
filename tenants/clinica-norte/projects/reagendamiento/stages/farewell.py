"""Farewell: confirm the new appointment out loud, promise the SMS, and close the call."""

from convo.agents import TenantAgent
from convo.domain.context import TenantContext
from convo.prompting import stage_prompt


class Farewell(TenantAgent):
    """Reads the new appointment back, mentions the SMS and says goodbye. No tools."""

    def __init__(self, tc: TenantContext) -> None:
        super().__init__(tc, instructions=stage_prompt(tc, "farewell"))

    def summary(self) -> str:
        """The last stage of the call; nothing downstream reads this, but the shape holds."""
        return "La llamada se ha cerrado tras confirmar la cita nueva."
