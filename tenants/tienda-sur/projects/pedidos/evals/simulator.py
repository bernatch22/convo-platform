"""Three order calls nobody scripted: a simulated customer against the real OrderDesk stage.

A golden is a sentence somebody wrote down because they thought of it. The
conversation that breaks "never cancel before a yes" is the one nobody thought
of — the customer who backs out at the exact moment the amount is read to them,
or the one who insists on cancelling something that already left the warehouse.
DeepEval's `ConversationSimulator` writes the customer's next line from a
persona and the transcript so far; everything on the other side of the line is
the real thing, the same `AgentSession`, tools, guard and saga a phone call gets.

Three decisions, the same ones the clinic's simulator made and for the same
reasons:

- **The calls start at `OrderDesk`, already identified.** Every user turn is a
  Haiku call for the persona and another for the agent, and identification is
  already pinned by `tests/test_tienda_stages.py` with two deterministic turns.
  `cancel_order` only exists in the stage these calls start in.
- **One live session per conversation** (`live_conversation`), never a replay:
  replaying re-generates the replies the customer was answering.
- **The stopping controller is deterministic.** Two tool names answer "is this
  call settled?" — `cancel_order` means the order was stopped, `decline` means
  the customer said no to it — so no judge is paid per turn to decide it.

Open source note: `OrderCaller` is the reusable half and it is a copy of the
clinic's `ReschedulingCaller` with two lines changed (the context and the
stage). That duplication is the argument for lifting it into
`core.testing.deepeval` next, which is a card, not a smuggled refactor.
"""

import os
from contextlib import AsyncExitStack

from deepeval.dataset import ConversationalGolden, Persona
from deepeval.models import AnthropicModel
from deepeval.simulator import ConversationSimulator
from deepeval.simulator.controller import end, proceed
from deepeval.simulator.controller.types import Decision
from deepeval.test_case import ConversationalTestCase, Turn
from deepeval.utils import get_or_create_event_loop

from core.context import TenantContext
from core.testing import LiveCall, fake_context, live_conversation, text_of
from core.testing.deepeval import conversational_test_case_for, tool_descriptions, turn_tool_calls

from ..stages import Identify, OrderDesk

TENANT, PROJECT = "tienda-sur", "pedidos"
MARTA = "TS-10432"  # seeded, still in the warehouse: the order these calls try to cancel
JAVIER = "TS-10433"  # seeded, already shipped: the order that cannot be cancelled at all

SIMULATOR_MODEL = os.getenv("DEEPEVAL_JUDGE_MODEL", "claude-haiku-4-5")
MAX_USER_TURNS = 4
CANCELLED, DECLINED = "cancel_order", "decline"

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
    caller = OrderCaller([MARTA, MARTA, JAVIER])
    cards = goldens()
    simulator = ConversationSimulator(
        model_callback=caller.answer,
        simulator_model=AnthropicModel(model=SIMULATOR_MODEL),
        stopping_controller=stop_when_the_order_is_settled,
        language="Spanish",
        # One at a time: it keeps the calls in golden order (which is how they are paired
        # back up below) and three sessions talking to Anthropic at once buys nothing.
        max_concurrent=1,
    )
    loop = get_or_create_event_loop()
    try:
        simulator.simulate(cards, max_user_simulations=MAX_USER_TURNS)
    finally:
        loop.run_until_complete(caller.hang_up())
    return caller.cases(cards)


def stop_when_the_order_is_settled(last_assistant_turn: Turn | None) -> Decision:
    """End the call the moment the order is cancelled or refused — no judge, two tool names."""
    if last_assistant_turn is None:
        return proceed()
    called = {tool.name for tool in last_assistant_turn.tools_called or []}
    if CANCELLED in called:
        return end("the order was cancelled")
    if DECLINED in called:
        return end("the customer did not confirm")
    return proceed()


class OrderCaller:
    """The shop's agent, as one live call per simulated conversation.

    DeepEval hands a callback one user line at a time and expects the
    assistant's answer back, with no notion of a session behind it. The
    `thread_id` it passes is the only thing that says which conversation a line
    belongs to, so it is what the open calls are keyed by — and the orders are
    handed out in golden order, one per conversation, as they open.
    """

    def __init__(self, orders: list[str]) -> None:
        self._orders = list(orders)
        self._sessions = AsyncExitStack()
        self._calls: dict[str, LiveCall] = {}
        self._order: list[str] = []
        self._descriptions: dict[str, str] = {}

    async def answer(self, input: str, thread_id: str) -> Turn:
        """One line from the customer in, the stage's whole answer out, tools and all."""
        call = self._calls.get(thread_id) or await self._open(thread_id)
        result = await call.say(input)
        return Turn(
            role="assistant",
            content=text_of(result),
            tools_called=turn_tool_calls(call.conversation.exchanges[-1]),
        )

    async def hang_up(self) -> None:
        """Close every session that is still open; conversations stay readable afterwards."""
        await self._sessions.aclose()

    def cases(self, cards: list[ConversationalGolden]) -> list[ConversationalTestCase]:
        """Each conversation as a multi-turn case, carrying the golden that drove it."""
        if len(self._order) != len(cards):
            raise AssertionError(
                f"{len(self._order)} conversations ran for {len(cards)} goldens: "
                "a simulated call produced no user turn at all"
            )
        return [
            conversational_test_case_for(
                self._calls[thread].conversation,
                self._descriptions,
                scenario=card.scenario,
                expected_outcome=card.expected_outcome,
                name=card.name,
            )
            for thread, card in zip(self._order, cards, strict=True)
        ]

    async def _open(self, thread_id: str) -> LiveCall:
        """Start a call for a conversation the simulator has just begun."""
        tc = identified_context(self._orders[len(self._order)])
        self._descriptions = self._descriptions or tool_descriptions(tc)
        call = await self._sessions.enter_async_context(live_conversation(tc, OrderDesk(tc)))
        self._calls[thread_id] = call
        self._order.append(thread_id)
        return call


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
