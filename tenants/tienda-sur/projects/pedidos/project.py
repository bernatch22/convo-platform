"""Pedidos: where an order is, and stopping it while there is still time.

The shop's half of ms-5. Same runtime as the clinic, same stages-and-saga
shape, and every single thing that differs is data in this folder: the tools
below, the knowledge block, the prompts, the voice, the failure sentences and
the register — a shop says "tú".

The catalog is the whole of what this project may call. It is data the platform
reads before every call, not documentation: a tool missing from here cannot
run, however convincingly the model asks for it, and the side effect declared
on each spec is what decides whether a customer has to say yes first.

`platform_specs()` is deliberately not merged in. The platform's inherited
catalog still carries `find_availability` from ms-2, an agenda tool this shop
has no system for; declaring a tool no adapter can serve buys a project a
spoken failure instead of a refusal, and the refusal is the honest answer.
"""

from dataclasses import dataclass
from pathlib import Path

from convo.domain.catalog import ToolCatalog
from convo.domain.context import Project, TenantContext
from convo.domain.tools import SideEffect, ToolSpec
from convo.telephony.human import TRANSFER_TO_HUMAN

from ...adapters.tickets import summarise_ticket
from .messages import MESSAGES

FIND_ORDER = ToolSpec(
    name="find_order",
    side_effect=SideEffect.READ,
    pii_scope=frozenset({"phone"}),
    timeout_s=5.0,
)
CANCEL_ORDER = ToolSpec(
    name="cancel_order",
    side_effect=SideEffect.IRREVERSIBLE,
    idempotency_key="order_id",
    compensation="restore_order",
    timeout_s=8.0,
)
# The undo of a cancellation is a write, never an irreversible: the platform is putting
# the order back the way the customer left it because we could not tell them it had been
# stopped, and asking for a second yes to do that is not a conversation anybody wants.
RESTORE_ORDER = ToolSpec(
    name="restore_order",
    side_effect=SideEffect.WRITE,
    idempotency_key="order_id",
    timeout_s=5.0,
)
SEND_SMS = ToolSpec(
    name="send_sms",
    side_effect=SideEffect.WRITE,
    pii_scope=frozenset({"phone"}),
    timeout_s=5.0,
)
# Opening an incident is a WRITE and not an irreversible, and the distinction is the
# whole reason the platform declares one: a ticket opened by mistake is closed by the
# team that reads it, and nothing happened to the customer's money, their parcel or
# their data. Asking a person to say yes out loud before we write down the problem they
# just described would be asking them to consent to being listened to. `cancel_order`
# stays irreversible, so the shop's consent metric still watches exactly one door.
#
# `subject` is free text a customer dictated, which is the widest PII surface in this
# project — an address, a neighbour's name, somebody else's order. It is masked in the
# log by declaration, and `summarise_ticket` never hands it to a renderer at all.
OPEN_TICKET = ToolSpec(
    name="open_ticket",
    side_effect=SideEffect.WRITE,
    pii_scope=frozenset({"subject", "phone", "name"}),
    timeout_s=6.0,
    result_summary=summarise_ticket,
)
TICKET_STATUS = ToolSpec(
    name="ticket_status",
    side_effect=SideEffect.READ,
    pii_scope=frozenset({"phone"}),
    timeout_s=5.0,
)


HERE = Path(__file__).parent


@dataclass
class PedidosProject(Project):
    """Project with an entry agent factory; the stages are the three phases of the call."""

    def entry_agent(self, tc: TenantContext):
        """The first stage a caller meets: the one that finds out which order this is about."""
        from .stages import Identify

        return Identify(tc)

    def stages(self, tc: TenantContext) -> list:
        """Every stage of the call, in order — the project's whole tool surface for evals."""
        from .stages import Farewell, Identify, OrderDesk, TicketDesk

        return [Identify(tc), OrderDesk(tc), TicketDesk(tc), Farewell(tc)]


PROJECT = PedidosProject(
    id="pedidos",
    name="Pedidos e incidencias",
    language="es-ES",
    # Art. 50 AI Act, same as the clinic: the greeting itself is the disclosure.
    greeting="¡Hola! Soy la asistente virtual de Tienda Sur. ¿En qué te ayudo?",
    voice="gD1IexrzCvsXPHUuT0s3",  # ElevenLabs "Sara Martin - 3": the shop's own voice
    # `TRANSFER_TO_HUMAN` is declared and `transfer_number` is deliberately unset: this
    # shop has no switchboard to hand a call to, so the model is never offered the verb and
    # the console says which of the two halves is missing. Opting in is the catalog line;
    # turning it on is one field the console owns (`core.telephony.human`).
    tools=ToolCatalog.of(
        FIND_ORDER,
        CANCEL_ORDER,
        RESTORE_ORDER,
        SEND_SMS,
        OPEN_TICKET,
        TICKET_STATUS,
        TRANSFER_TO_HUMAN,
    ),
    messages=MESSAGES,
    knowledge_seed=(HERE / "knowledge.md").read_text(),
    knowledge_tag="shop_knowledge",
    prompts=HERE / "prompts",
)
