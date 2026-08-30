"""Reagendamiento: reschedule an existing appointment.

ms-3 turns the conversation into a process — Identify, ChooseSlot, Farewell —
and gives it the right to write: `book_slot` is irreversible and unreachable
without a confirmation token, and the three writes that make up a rebooking run
as a saga so a failure halfway leaves the patient's old appointment standing.

The catalog below is the whole of what this project may call. It is data the
platform reads before every call, not documentation: a tool missing from here
cannot run, however convincingly the model asks for it, and the side effect
declared on each spec is what decides whether a caller has to say yes first.
"""

from dataclasses import dataclass

from core.context import Project, TenantContext
from core.tools.catalog import ToolCatalog, platform_specs
from core.tools.contract import SideEffect, ToolSpec
from core.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL

from . import knowledge

FIND_PATIENT = ToolSpec(
    name="find_patient",
    side_effect=SideEffect.READ,
    pii_scope=frozenset({"phone", "name"}),
    timeout_s=5.0,
)
CANCEL_SLOT = ToolSpec(
    name="cancel_slot",
    side_effect=SideEffect.WRITE,
    idempotency_key="appointment_id",
    compensation="rebook_slot",
    timeout_s=5.0,
)
BOOK_SLOT = ToolSpec(
    name="book_slot",
    side_effect=SideEffect.IRREVERSIBLE,
    idempotency_key="slot_id",
    pii_scope=frozenset({"phone", "patient"}),
    compensation="cancel_slot",
    timeout_s=8.0,
)
# The undo of a cancel is a write, never an irreversible: the platform is putting
# things back the way the patient left them, and asking for a second yes to do
# that is not a conversation anybody wants.
REBOOK_SLOT = ToolSpec(
    name="rebook_slot",
    side_effect=SideEffect.WRITE,
    idempotency_key="appointment_id",
    timeout_s=5.0,
)
SEND_SMS = ToolSpec(
    name="send_sms",
    side_effect=SideEffect.WRITE,
    pii_scope=frozenset({"phone"}),
    timeout_s=5.0,
)

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
        """The first stage a caller meets: the one that finds out whose appointment this is."""
        from .stages import Identify

        return Identify(tc)

    def stages(self, tc: TenantContext) -> list:
        """Every stage of the call, in order — the project's whole tool surface for evals."""
        from .stages import ChooseSlot, Farewell, Identify

        return [Identify(tc), ChooseSlot(tc), Farewell(tc)]


PROJECT = ReagendamientoProject(
    id="reagendamiento",
    name="Reagendamiento de citas",
    language="es-ES",
    voice="UOIqAnmS11Reiei1Ytkc",  # ElevenLabs "Carolina - Spanish woman - es_ES" (used from ms-6)
    tools=platform_specs().merge(
        ToolCatalog.of(FIND_PATIENT, CANCEL_SLOT, BOOK_SLOT, REBOOK_SLOT, SEND_SMS)
    ),
    messages=MESSAGES,
    knowledge_seed=knowledge.CLINIC,
)
