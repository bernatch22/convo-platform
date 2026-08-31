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

from core.context import Project, TenantContext
from core.tools.catalog import ToolCatalog
from core.tools.contract import SideEffect, ToolSpec
from core.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL

from . import knowledge

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

# When a tool call cannot produce a result the model still has to say something. The
# platform's defaults already address the caller as "tú", but they talk about "sistemas";
# a shop talks about its almacén, so the sentences are written here, next to the prompt
# that established the voice.
MESSAGES = {
    UNKNOWN_TOOL: "Eso no lo puedo mirar yo desde aquí. ¿Te ayudo con tu pedido?",
    NO_ADAPTER: "No puedo entrar ahora mismo en el sistema de pedidos. ¿Te llamamos luego?",
    TIMEOUT: "El sistema de pedidos está tardando en contestar. ¿Lo intento otra vez?",
    FAILURE: "No he podido consultar tu pedido. ¿Quieres que lo intente de nuevo?",
}


@dataclass
class PedidosProject(Project):
    """Project with an entry agent factory; the stages are the three phases of the call."""

    def entry_agent(self, tc: TenantContext):
        """The first stage a caller meets: the one that finds out which order this is about."""
        from .stages import Identify

        return Identify(tc)

    def stages(self, tc: TenantContext) -> list:
        """Every stage of the call, in order — the project's whole tool surface for evals."""
        from .stages import Farewell, Identify, OrderDesk

        return [Identify(tc), OrderDesk(tc), Farewell(tc)]


PROJECT = PedidosProject(
    id="pedidos",
    name="Estado y cancelación de pedidos",
    language="es-ES",
    greeting="¡Hola! Soy la asistente de Tienda Sur. ¿En qué te ayudo?",
    voice="gD1IexrzCvsXPHUuT0s3",  # ElevenLabs "Sara Martin - 3": the shop's own voice
    tools=ToolCatalog.of(FIND_ORDER, CANCEL_ORDER, RESTORE_ORDER, SEND_SMS),
    messages=MESSAGES,
    knowledge_seed=knowledge.SHOP,
)
