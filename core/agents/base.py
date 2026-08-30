"""TenantAgent: the base every project stage extends. Projects never import livekit directly."""

import logging

from livekit.agents import Agent

from core.context import TenantContext

log = logging.getLogger("platform.agents")


class TenantAgent(Agent):
    """One conversation stage of a project, with its own prompt and (later) tools."""

    def __init__(self, tc: TenantContext, *, instructions: str, **kwargs) -> None:
        super().__init__(instructions=instructions, **kwargs)
        self.tc = tc

    async def on_enter(self) -> None:
        """Announce the stage and let the model open the turn (greeting or next question)."""
        log.info("stage.enter %s agent=%s", self.tc.label(), self.stage_name())
        self.tc.prev_agent = self
        self.session.generate_reply()

    def stage_name(self) -> str:
        """The stage as it appears in logs and, from ms-4, in the event log."""
        return type(self).__name__
