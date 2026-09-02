"""ConfirmTask: ask the caller to confirm one concrete action, and mint the token if they do.

Decisions: docs/decisions/convo.agents.confirm_task.md
"""

import logging
from typing import Any

from livekit.agents import RunContext, function_tool
from livekit.agents.voice import AgentTask

from convo.state.log import record
from convo.tools import confirm

log = logging.getLogger("platform.confirm")

INSTRUCTIONS = (
    "Estás confirmando una acción que no se puede deshacer. Ya has hecho la pregunta, "
    "con estas palabras exactas: «{question}». Ahora solo escuchas la respuesta. Si la "
    "persona dice que sí con claridad, llama a confirm. Si dice que no, duda, cambia de "
    "tema o pide otra cosa, llama a decline. No des por hecho un sí: un silencio o un "
    "«mmm» no lo es. No repitas la pregunta ni saludes: la llamada ya está en curso."
)


class ConfirmTask(AgentTask[bool]):
    """Asks `question` about `tool(args)`; True mints the token onto the context, False does not."""

    def __init__(
        self,
        tc: Any,
        *,
        question: str,
        tool: str,
        args: dict[str, Any],
        instructions: str | None = None,
    ) -> None:
        # No `tools=` argument: an Agent collects its own @function_tool methods, and
        # passing them as well registers each one twice — which LiveKit refuses with
        # "duplicate function name: confirm" the moment the task takes over the session.
        super().__init__(instructions=(instructions or INSTRUCTIONS).format(question=question))
        self.tc = tc
        self.tool = tool
        self.args = args
        self.question = question

    async def on_enter(self) -> None:
        """Speak the rendered question verbatim as soon as the task takes over."""
        log.info("confirm.ask %s tool=%s", self.tc.label(), self.tool)
        # The audience digest, never the arguments: it names the exact call the
        # caller is being asked about without putting a phone number in the log.
        record(self.tc, "confirm.request", self._audit(question=self.question))
        self.session.say(self.question, allow_interruptions=True)

    @function_tool
    async def confirm(self, ctx: RunContext) -> None:
        """La persona ha dicho que sí, claramente, a la pregunta que le has hecho."""
        confirm.mint(self.tc, self.tool, self.args)
        log.info("confirm.yes %s tool=%s", self.tc.label(), self.tool)
        record(self.tc, "confirm.granted", self._audit())
        self.complete(True)

    @function_tool
    async def decline(self, ctx: RunContext) -> None:
        """La persona no ha dicho que sí: ha dicho que no, duda, o quiere otra cosa."""
        log.info("confirm.no %s tool=%s", self.tc.label(), self.tool)
        record(self.tc, "confirm.declined", self._audit())
        self.complete(False)

    def _audit(self, **extra: Any) -> dict[str, Any]:
        """What every confirm event says: which call, by tool and audience digest."""
        return {"tool": self.tool, "audience": confirm.audience(self.tool, self.args), **extra}
