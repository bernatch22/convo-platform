"""Reagendamiento: reschedule an existing appointment. ms-2: reception can read the agenda."""

from dataclasses import dataclass

from core.context import Project, TenantContext
from core.tools.catalog import platform_specs
from core.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL

# When a tool call cannot produce a result the model still has to say something,
# and the platform's defaults address the caller as "tú". Clínica Norte speaks
# to patients as "usted", so the register is set here, next to the prompt that
# established it, rather than in core.
MESSAGES = {
    UNKNOWN_TOOL: "Eso no puedo consultarlo desde aquí. ¿Le ayudo con su cita?",
    NO_ADAPTER: "No puedo entrar en la agenda ahora mismo. ¿Prefiere que le llamemos hoy?",
    TIMEOUT: "La agenda está tardando en responder. ¿Lo intento otra vez?",
    FAILURE: "No he podido consultar la agenda. ¿Quiere que lo intente de nuevo?",
}


@dataclass
class ReagendamientoProject(Project):
    """Project with an entry agent factory; voice and keyterms arrive with later milestones."""

    def entry_agent(self, tc: TenantContext):
        """The first stage a caller meets."""
        from .agents import Reception

        return Reception(tc)


PROJECT = ReagendamientoProject(
    id="reagendamiento",
    name="Reagendamiento de citas",
    language="es-ES",
    voice="UOIqAnmS11Reiei1Ytkc",  # ElevenLabs "Carolina - Spanish woman - es_ES" (used from ms-6)
    tools=platform_specs(),
    messages=MESSAGES,
)
