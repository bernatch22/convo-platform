"""Three order calls nobody scripted: who calls, what should happen, where the call starts.

Decisions: docs/decisions/tenants.tienda-sur.projects.pedidos.evals.simulator.md
"""

from deepeval.dataset import ConversationalGolden, Persona
from deepeval.test_case import ConversationalTestCase

from convo.domain.context import TenantContext
from convo.testing import fake_context
from convo.testing.callers.simulator import SimulatedCaller, settled_when

from ..stages import Identify, OrderDesk

TENANT, PROJECT = "tienda-sur", "pedidos"
MARTA = "TS-10432"  # seeded, still in the warehouse: the order these calls try to cancel
JAVIER = "TS-10433"  # seeded, already shipped: the order that cannot be cancelled at all

MAX_USER_TURNS = 4
SETTLED = {
    "cancel_order": "the order was cancelled",
    "decline": "the customer did not confirm",
}

VOICE = (
    "Hablas español de España, por teléfono, en frases cortas. Nunca escribes acotaciones ni "
    "describes lo que haces: dices tu frase y nada más. Ya te han localizado el pedido al "
    "empezar la llamada, así que no repitas el número si no te lo piden."
)

DECIDED = Persona(
    name="Marta, lo tiene claro",
    characteristics=(
        "Eres Marta Alonso Gil y llamas a Tienda Sur para cancelar tu pedido, que te has "
        f"equivocado de talla. {VOICE} Pides la cancelación y, cuando te lean el pedido y el "
        "importe y te pregunten si lo cancelan, dices que sí con claridad."
    ),
)
BACKS_OUT = Persona(
    name="Marta, se echa atrás",
    characteristics=(
        "Eres Marta Alonso Gil y llamas a Tienda Sur porque estás pensando en cancelar tu "
        f"pedido. {VOICE} Pides que te lo cancelen, pero en cuanto te lean el pedido para "
        "confirmarlo te echas atrás: dices que no, que mejor esperas a verlo. No confirmas "
        "nada, pase lo que pase."
    ),
)
INSISTS = Persona(
    name="Javier, insiste con uno ya enviado",
    characteristics=(
        "Eres Javier Nieto Salas y llamas a Tienda Sur para cancelar tu pedido, que ya te han "
        f"enviado. {VOICE} Cuando te digan que ya ha salido y no se puede cancelar, insistes "
        "una vez más —«pero cancélamelo, aún no me ha llegado»— y luego aceptas lo que te "
        "ofrezcan."
    ),
)

CANCELLED_OUTCOME = "El pedido queda cancelado y el cliente lo sabe."
NOTHING_CANCELLED = "No se cancela nada y el pedido que el cliente tenía sigue en pie."

# Which seeded order each call is about. By golden name rather than by position: the
# order is the scenario, and a golden that moves in the list must not change customer.
ORDER_OF = {
    "cancela-y-confirma": MARTA,
    "se-echa-atras": MARTA,
    "ya-enviado-e-insiste": JAVIER,
}


def goldens() -> list[ConversationalGolden]:
    """The three calls to simulate: one that cancels, one that backs out, one that cannot."""
    return [
        ConversationalGolden(
            name="cancela-y-confirma",
            scenario="La clienta quiere cancelar su pedido, que todavía se está preparando.",
            expected_outcome=CANCELLED_OUTCOME,
            persona=DECIDED,
        ),
        ConversationalGolden(
            name="se-echa-atras",
            scenario="La clienta pide cancelar y se arrepiente al oír el pedido entero.",
            expected_outcome=NOTHING_CANCELLED,
            persona=BACKS_OUT,
        ),
        ConversationalGolden(
            name="ya-enviado-e-insiste",
            scenario="El cliente quiere cancelar un pedido que ya ha salido del almacén.",
            expected_outcome=NOTHING_CANCELLED,
            persona=INSISTS,
        ),
    ]


def simulate_calls() -> list[ConversationalTestCase]:
    """Run every golden once and return the conversations as multi-turn cases, in that order."""
    return SimulatedCaller(
        goldens(),
        lambda golden: identified_context(ORDER_OF[golden.name]),
        OrderDesk,
        stop_when=settled_when(SETTLED),
        max_user_turns=MAX_USER_TURNS,
    ).simulate()


def identified_context(order_id: str) -> TenantContext:
    """A session that has already found one seeded order: exactly where OrderDesk begins."""
    tc = fake_context(TENANT, PROJECT)
    tc.customer = {"order_id": order_id, **tc.adapters["orders"].book[order_id]}
    tc.prev_agent = Identify(tc)
    return tc
