"""ConfirmTask: ask the caller to confirm one concrete action, and mint the token if they do.

An `AgentTask` takes the conversation over for as long as it needs: it asks
one question with its own tiny prompt and two tools, and returns a result to
the tool that awaited it. This one returns True or False; on True it has
already minted a `ConfirmationToken` for exactly the call the stage is about
to make, so the guard lets that call — and only that call — through.

A new instance per use: an AgentTask is not re-entrant, and neither is a yes.

Open source note: the question and the two tool docstrings are the only
Spanish in this file; a project in another language passes its own
`instructions` and the tools' behaviour is unchanged.
"""

import logging
from typing import Any

from livekit.agents import RunContext, function_tool
from livekit.agents.voice import AgentTask

from core import confirm

log = logging.getLogger("platform.confirm")

INSTRUCTIONS = (
    "Estás confirmando una acción que no se puede deshacer. Pregunta exactamente "
    "esto, con estas palabras, y nada más: «{question}». Si la persona dice que sí "
    "con claridad, llama a confirm. Si dice que no, duda, cambia de tema o pide otra "
    "cosa, llama a decline. No des por hecho un sí: un silencio o un «mmm» no lo es."
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
        """Ask the question as soon as the task takes over."""
        log.info("confirm.ask %s tool=%s", self.tc.label(), self.tool)
        self.session.generate_reply()

    @function_tool
    async def confirm(self, ctx: RunContext) -> None:
        """La persona ha dicho que sí, claramente, a la pregunta que le has hecho."""
        confirm.mint(self.tc, self.tool, self.args)
        log.info("confirm.yes %s tool=%s", self.tc.label(), self.tool)
        self.complete(True)

    @function_tool
    async def decline(self, ctx: RunContext) -> None:
        """La persona no ha dicho que sí: ha dicho que no, duda, o quiere otra cosa."""
        log.info("confirm.no %s tool=%s", self.tc.label(), self.tool)
        self.complete(False)
