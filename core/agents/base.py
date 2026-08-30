"""TenantAgent: the base every project stage extends. Projects never import livekit directly.

A conversation is a sequence of stages, one Agent each. LiveKit does not copy
history across a handoff, so the stage that enters writes a one-line summary of
the stage it replaces into its own chat context before saying anything: what
the caller already told us travels, the whole transcript does not.
"""

import logging

from livekit.agents import Agent
from livekit.agents.llm import ChatContext

from core.context import TenantContext

log = logging.getLogger("platform.agents")

SUMMARY_ROLE = "system"


class TenantAgent(Agent):
    """One conversation stage of a project, with its own prompt and tools."""

    def __init__(self, tc: TenantContext, *, instructions: str, **kwargs) -> None:
        super().__init__(instructions=instructions, **kwargs)
        self.tc = tc

    async def on_enter(self) -> None:
        """Inherit the previous stage's summary, announce the stage, let the model open the turn."""
        await self._inherit_summary()
        log.info("stage.enter %s agent=%s", self.tc.label(), self.stage_name())
        self.tc.prev_agent = self
        self.session.generate_reply()

    def summary(self) -> str:
        """One prose line the next stage reads about what happened here; stages override it."""
        return f"Etapa anterior: {self.stage_name()}."

    def hand_off(self, next_agent: "TenantAgent", said: str) -> tuple[Agent, str]:
        """What a tool returns to move the conversation on: the next stage and what to say."""
        log.info(
            "stage.handoff %s %s -> %s",
            self.tc.label(),
            self.stage_name(),
            next_agent.stage_name(),
        )
        return next_agent, said

    def stage_name(self) -> str:
        """The stage as it appears in logs and, from ms-4, in the event log."""
        return type(self).__name__

    async def _inherit_summary(self) -> None:
        previous = self.tc.prev_agent
        if previous is None or previous is self or not hasattr(previous, "summary"):
            return
        chat_ctx: ChatContext = self.chat_ctx.copy()
        chat_ctx.add_message(role=SUMMARY_ROLE, content=previous.summary())
        await self.update_chat_ctx(chat_ctx)
