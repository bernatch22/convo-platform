"""TenantAgent: the base every project stage extends. Projects never import livekit directly.

Decisions: docs/decisions/convo.agents.stage.md
"""

import logging
from collections.abc import AsyncGenerator, AsyncIterable

from livekit import rtc
from livekit.agents import Agent, RunContext, StopResponse, stt
from livekit.agents.llm import ChatContext, ChatMessage, function_tool
from livekit.agents.voice.agent import ModelSettings

from convo.agents.clock import clock_reading, date_note
from convo.agents.human import transfer_tools
from convo.domain.context import TenantContext
from convo.observability.voice import TimedWords
from convo.providers.tts import tts_for
from convo.session.barge_in import backchannels_of, holds_the_floor, is_backchannel
from convo.session.stt_gate import TranscriptGate, gate_options_for
from convo.state.log import record

log = logging.getLogger("platform.agents")

SUMMARY_ROLE = "system"

# The first line of every inherited summary, and the only one the platform writes.
# A stage's prompt teaches it to open a call, because for the first stage that is
# exactly right; reached by a handoff, the same prompt greets a caller who has been
# talking for two minutes, and a call that says "Tienda Sur, buenos días" for the
# third time sounds like it restarted (real session, 2026-09-01: a customer bounced
# between the order desk and the incident desk was greeted at every arrival). Only
# the platform knows whether this stage is the beginning, so this sentence is the
# platform's and not a rule each project has to remember to write.
MID_CALL = (
    "La llamada ya viene de antes y tú no eres el principio: no saludes, no te presentes, "
    "no digas el nombre del negocio otra vez y no vuelvas a preguntar lo que ya te han dicho. "
    "Sigue donde se quedó. Lo que va detrás de esta frase es una nota interna para ti: no la "
    "leas en voz alta, no la resumas, no la comentes y no hables del cliente en tercera "
    "persona. Le hablas a él, directamente, de lo que te acaba de decir."
)


class TenantAgent(Agent):
    """One conversation stage of a project, with its own prompt and tools."""

    def __init__(
        self, tc: TenantContext, *, instructions: str, tools: list | None = None, **kwargs
    ) -> None:
        # The platform's own verbs are layered here, not declared as methods, so
        # that one of them can be ABSENT: a project with no `transfer_number`
        # must never be shown a transfer tool it cannot run (`convo.agents.human`).
        platform = transfer_tools(tc)
        super().__init__(
            instructions=instructions,
            tools=[*(tools or []), *platform],
            **self._own_voice(tc),
            **kwargs,
        )
        self.tc = tc

    async def on_enter(self) -> None:
        """Read the clock, inherit the previous summary, announce the stage, open the turn."""
        await self._read_the_clock()
        await self._inherit_summary()
        log.info("stage.enter %s agent=%s", self.tc.label(), self.stage_name())
        record(self.tc, "stage.enter", {"stage": self.stage_name()})
        opener = self.tc.project.greeting if self.tc.prev_agent is None else None
        self.tc.prev_agent = self
        if opener:
            self.session.say(opener, allow_interruptions=True)
        else:
            self.session.generate_reply()

    async def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncGenerator[stt.SpeechEvent, None]:
        """Transcribe as the framework does, dropping a transcript the audio cannot account for."""
        gate = TranscriptGate(gate_options_for(self.tc.project))
        async for event in super().stt_node(gate.hear(audio), model_settings):
            if gate.accepts(event):
                yield event
                continue
            evidence = gate.evidence(event)
            log.warning("stt.phantom %s %s", self.tc.label(), evidence)
            record(self.tc, "stt.phantom", evidence)

    async def transcription_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncGenerator[str, None]:
        """Forward the agent's transcription untouched, timing each word into the log."""
        words = TimedWords(self.tc)
        try:
            async for delta in text:
                words.add(delta)
                yield delta
        finally:
            words.flush()

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """Answer the caller — unless a human holds the line, or the turn was a murmur."""
        text = new_message.text_content or ""
        control = self.tc.supervisor
        if control is not None:
            await control.flush(self)
            if control.muted:
                log.info("turn.muted %s (a human holds the line) %r", self.tc.label(), text)
                raise StopResponse()
        if not holds_the_floor(self.session):
            return
        if not is_backchannel(text, backchannels_of(self.tc.project)):
            return
        log.info("turn.backchannel %s %r", self.tc.label(), text)
        record(self.tc, "turn.backchannel", {"text": text})
        raise StopResponse()

    @function_tool
    async def fecha_y_hora_actual(self, ctx: RunContext) -> str:
        """Consulta la fecha y la hora actuales, exactas, en este momento.

        Llámala siempre que el interlocutor pregunte qué día es, qué hora es, o
        cuando necesites la hora presente para responder. No calcules ni
        recuerdes la hora tú: cambia durante la llamada y esta herramienta la
        lee del reloj cada vez.
        """
        tc = self.tc
        return date_note(tc.today, tc.now())

    def summary(self) -> str:
        """One prose line the next stage reads about what happened here; stages override it."""
        return f"Etapa anterior: {self.stage_name()}."

    def hand_off(
        self, next_agent: "TenantAgent", said: str | None = None
    ) -> "Agent | tuple[Agent, str]":
        """What a tool returns to move the call on: the next stage, and optionally a last line."""
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

    def _own_voice(self, tc: TenantContext) -> dict:
        """This stage's own TTS when the project gave it one, or nothing at all."""
        voice = tc.project.stage_voices.get(type(self).__name__)
        if not voice:
            return {}
        speaker = tts_for(tc.tenant, tc.project, voice=voice)
        return {"tts": speaker} if speaker else {}

    async def _read_the_clock(self) -> None:
        """Once per session, put the day in front of the model — as evidence, not as a turn."""
        if self.tc.date_noted:
            return
        self.tc.date_noted = True
        chat_ctx: ChatContext = self.chat_ctx.copy()
        chat_ctx.insert(clock_reading(self.tc.today))
        await self.update_chat_ctx(chat_ctx)

    async def _inherit_summary(self) -> None:
        previous = self.tc.prev_agent
        if previous is None or previous is self or not hasattr(previous, "summary"):
            return
        chat_ctx: ChatContext = self.chat_ctx.copy()
        chat_ctx.add_message(role=SUMMARY_ROLE, content=f"{MID_CALL} {previous.summary()}")
        await self.update_chat_ctx(chat_ctx)
