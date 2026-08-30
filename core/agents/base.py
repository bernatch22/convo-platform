"""TenantAgent: the base every project stage extends. Projects never import livekit directly.

A conversation is a sequence of stages, one Agent each. LiveKit does not copy
history across a handoff, so the stage that enters writes a one-line summary of
the stage it replaces into its own chat context before saying anything: what
the caller already told us travels, the whole transcript does not.

Two of the framework's nodes are overridden here, once, for every project:
`transcription_node` reads the agent's words on their way out and times them in
the log, and `on_user_turn_completed` drops a murmur that landed on the agent's
voice. Both are audit and turn-taking, not business, so no stage overrides them.
"""

import logging
from collections.abc import AsyncGenerator, AsyncIterable

from livekit.agents import Agent, StopResponse
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.agents.voice.agent import ModelSettings

from core.barge_in import backchannels_of, holds_the_floor, is_backchannel
from core.context import TenantContext
from core.observability.voice import TimedWords
from core.state.log import record

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
        record(self.tc, "stage.enter", {"stage": self.stage_name()})
        self.tc.prev_agent = self
        self.session.generate_reply()

    async def transcription_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncGenerator[str, None]:
        """Forward the agent's transcription untouched, timing each word into the log.

        Every delta goes on exactly as it arrived — this node is where a
        project could rewrite what the caller reads, and rewriting it is
        precisely what an audit log must not do. With
        `use_tts_aligned_transcript=True` and ElevenLabs `sync_alignment=True`
        the deltas are `TimedString`s carrying `end_time`; `TimedWords` batches
        them into one `tts.word` event per sentence.
        """
        words = TimedWords(self.tc)
        try:
            async for delta in text:
                words.add(delta)
                yield delta
        finally:
            words.flush()

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """Answer the caller — unless the turn was a murmur over the agent's own voice.

        "vale" while the agent is mid-sentence is agreement, not a question,
        and a reply to it is a filler the caller hears as a mistake. The turn is
        recorded as `turn.backchannel` and `StopResponse` cancels the reply.

        It cannot cancel the interruption: `core.barge_in` documents where each
        of the two filters sits in the framework's turn pipeline, and why
        `InterruptionOptions.min_words` is the one that saves the audio.
        """
        text = new_message.text_content or ""
        if not holds_the_floor(self.session):
            return
        if not is_backchannel(text, backchannels_of(self.tc.project)):
            return
        log.info("turn.backchannel %s %r", self.tc.label(), text)
        record(self.tc, "turn.backchannel", {"text": text})
        raise StopResponse()

    def summary(self) -> str:
        """One prose line the next stage reads about what happened here; stages override it."""
        return f"Etapa anterior: {self.stage_name()}."

    def hand_off(
        self, next_agent: "TenantAgent", said: str | None = None
    ) -> "Agent | tuple[Agent, str]":
        """What a tool returns to move the conversation on: the next stage, and optionally a line.

        Default to no line. A tool that returns text alongside the next stage
        makes the stage that is LEAVING answer with it, and the stage arriving
        then speaks in its own `on_enter` — two turns, one after the other, and
        on a phone call that is the same thing said twice. What the next stage
        needs to know travels in `summary()`, not in a farewell sentence.

        Pass `said` only when the leaving stage genuinely has the last word.
        """
        log.info(
            "stage.handoff %s %s -> %s",
            self.tc.label(),
            self.stage_name(),
            next_agent.stage_name(),
        )
        record(
            self.tc,
            "stage.handoff",
            {"from": self.stage_name(), "to": next_agent.stage_name(), "said": said is not None},
        )
        return (next_agent, said) if said is not None else next_agent

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
