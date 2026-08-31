"""Three order calls nobody scripted: who calls, what should happen, where the call starts.

The machinery is `core.testing.simulator`, shared with the clinic next door. What
lives here is the shop's half of it, and only that: three personas, three
goldens, the two tool names that settle a cancellation, and the seeded order each
call starts from.

Two of those choices are worth the sentence:

- **The calls start at `OrderDesk`, already identified.** Every user turn is a
  Haiku call for the persona and another for the agent, and identification is
  already pinned by `tests/test_tienda_stages.py` with two deterministic turns.
  `cancel_order` only exists in the stage these calls start in.
- **`cancel_order` and `decline` end the call.** The first means the order was
  stopped, the second that the customer said no to it. Neither needs a judge.
"""

from deepeval.dataset import ConversationalGolden, Persona
from deepeval.test_case import ConversationalTestCase

from core.context import TenantContext
from core.testing import fake_context
from core.testing.simulator import SimulatedCaller, settled_when

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
    """A session that has already found one seeded order: exactly where OrderDesk begins.

    `prev_agent` matters as much as `customer`. What OrderDesk knows about the
    order arrives as the previous stage's `summary()` in its `on_enter`, and a
    stage entered without one opens by asking for the order number again — the
    right behaviour, and the wrong conversation to be simulating here.
    """
    tc = fake_context(TENANT, PROJECT)
    tc.customer = {"order_id": order_id, **tc.adapters["orders"].book[order_id]}
    tc.prev_agent = Identify(tc)
    return tc
