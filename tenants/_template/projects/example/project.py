"""Example: one use case of Example Co — find a booking and cancel it.

A project is everything about ONE thing a caller can ring about: the tools it
may use, the voice it speaks with, its knowledge block, the sentences it says
when a tool fails, and the stage the call starts in. A tenant with two use cases
has two of these folders and one `tenant.py`.

The catalog is data the platform reads before every call, not documentation: a
tool missing from here cannot run, however convincingly the model asks for it,
and the `side_effect` declared on each spec is what decides whether the customer
has to say yes first.

TODO(copy): one `ToolSpec` per capability this use case may reach, the voice,
and the failure sentences in your own register. Declare nothing you have no
adapter for — a tool with no system behind it buys a spoken failure where a
refusal would have been the honest answer.
"""

from dataclasses import dataclass
from pathlib import Path

from convo.domain.catalog import ToolCatalog
from convo.domain.context import Project, TenantContext
from convo.domain.tools import SideEffect, ToolSpec
from convo.telephony.human import TRANSFER_TO_HUMAN
from convo.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL

FIND_BOOKING = ToolSpec(
    name="find_booking",
    side_effect=SideEffect.READ,
    timeout_s=5.0,
)
# IRREVERSIBLE: the guard refuses this without a confirmation token minted by ConfirmTask,
# so it cannot run because the model decided the customer sounded sure.
CANCEL_BOOKING = ToolSpec(
    name="cancel_booking",
    side_effect=SideEffect.IRREVERSIBLE,
    idempotency_key="reference",
    compensation="restore_booking",
    timeout_s=8.0,
)
# The platform's own verb, not this business's: handing the live call to a person.
# Declaring it here is the opt-in; `transfer_number` below is what turns it on, and an
# empty one means the model is never offered the tool at all (`core.telephony.human`).
#
# The undo of a cancellation is a WRITE, never an irreversible: putting a booking back the
# way the customer left it must not need a second yes from them.
RESTORE_BOOKING = ToolSpec(
    name="restore_booking",
    side_effect=SideEffect.WRITE,
    idempotency_key="reference",
    timeout_s=5.0,
)

# What the caller hears when a tool cannot produce a result. The platform's defaults are in
# `core.tools.messages`; these override them in this business's own words and register.
MESSAGES = {
    UNKNOWN_TOOL: "Eso no puedo consultarlo yo. ¿Le ayudo con su reserva?",
    NO_ADAPTER: "No puedo entrar ahora mismo en el sistema de reservas. ¿Le llamamos luego?",
    TIMEOUT: "El sistema está tardando en contestar. ¿Lo intento otra vez?",
    FAILURE: "No he podido consultar su reserva. ¿Quiere que lo intente de nuevo?",
}


HERE = Path(__file__).parent


@dataclass
class ExampleProject(Project):
    """Project with an entry agent factory; the stages are the phases of the call."""

    def entry_agent(self, tc: TenantContext):
        """The first stage a caller meets: the one that finds out which booking this is."""
        from .stages import Reception

        return Reception(tc)

    def stages(self, tc: TenantContext) -> list:
        """Every stage of the call, in order — the project's whole tool surface for evals."""
        from .stages import Desk, Reception

        return [Reception(tc), Desk(tc)]


PROJECT = ExampleProject(
    id="example",
    name="Reservas",
    language="es-ES",
    voice="UOIqAnmS11Reiei1Ytkc",  # TODO(copy): the ElevenLabs voice id of this business
    tools=ToolCatalog.of(FIND_BOOKING, CANCEL_BOOKING, RESTORE_BOOKING, TRANSFER_TO_HUMAN),
    # TODO(copy): the E.164 number a call is handed to when the caller asks for a person.
    # Empty means the agent is never offered the verb, which is the honest default for a
    # business with nobody on the other end of it.
    transfer_number="",
    messages=MESSAGES,
    knowledge_seed=(HERE / "knowledge.md").read_text(),
    knowledge_tag="business_knowledge",
    prompts=HERE / "prompts",
)
