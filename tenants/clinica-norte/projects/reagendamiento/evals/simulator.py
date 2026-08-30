"""Five rescheduling calls nobody scripted: a simulated patient against the real ChooseSlot stage.

A golden is a sentence somebody wrote down because they thought of it. The
conversation that breaks "never book before a yes" is the one nobody thought
of — the patient who changes their mind twice, or who backs out at the exact
moment the hour is read to them. DeepEval's `ConversationSimulator` writes the
patient's next line from a persona and the transcript so far; everything on the
other side of the line is the real thing, the same `AgentSession`, tools, guard
and saga a phone call gets.

Three decisions that keep this affordable and honest, all of them reversible:

- **The calls start at `ChooseSlot`, already identified.** Every user turn is a
  Haiku call for the persona and another for the agent, and identification is
  already pinned by `tests/test_stages.py` with two deterministic turns. Paying
  five conversations' worth of model time to re-prove it would buy nothing this
  metric can read: `book_slot` only exists in the stage these calls start in.
- **One live session per conversation** (`live_conversation`), never a replay.
  The reason is in the harness: replaying re-generates the replies the patient
  was answering.
- **The stopping controller is deterministic.** DeepEval's default asks a judge
  after every turn whether the expected outcome has been reached. Two tool
  names already answer it: `book_slot` means the change went through,
  `decline` means the patient said no to it. That is a judge call per turn per
  conversation saved, for a question with no judgement in it.

Open source note: `ReschedulingCaller` is the reusable half — any project with
a `TenantContext` and a stage swaps the two lines that build them and gets a
simulated caller. The personas and the seeded patient below are Clínica Norte's.
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

from ..stages import ChooseSlot, Identify

TENANT, PROJECT = "clinica-norte", "reagendamiento"
ANA = "ap-20260903-1000-trau"  # the seeded appointment every simulated call reschedules

SIMULATOR_MODEL = os.getenv("DEEPEVAL_JUDGE_MODEL", "claude-haiku-4-5")
MAX_USER_TURNS = 6
BOOKED, DECLINED = "book_slot", "decline"

VOICE = (
    "Hablas español de España, por teléfono, en frases cortas. Nunca escribes acotaciones ni "
    "describes lo que haces: dices tu frase y nada más. Ya te han identificado al empezar la "
    "llamada, así que no repitas tu nombre ni tu teléfono si no te los piden."
)

COOPERATIVE = Persona(
    name="Ana, va al grano",
    characteristics=(
        "Eres Ana García Ruiz, paciente de Clínica Norte, y llamas para cambiar tu cita de "
        f"traumatología. {VOICE} Dices el día que quieres, eliges una de las horas que te "
        "ofrezcan y, cuando te lean la hora entera y te pregunten si la confirman, dices que "
        "sí con claridad."
    ),
)
CHANGES_MIND = Persona(
    name="Ana, cambia de idea dos veces",
    characteristics=(
        "Eres Ana García Ruiz, paciente de Clínica Norte, y llamas para cambiar tu cita de "
        f"traumatología. {VOICE} Pides primero un día; cuando te ofrezcan horas, dices que "
        "mejor el otro día; cuando te ofrezcan las de ese otro, vuelves a preferir el primero. "
        "Después eliges una hora y, si te la leen para confirmarla, dices que sí."
    ),
)
BACKS_OUT = Persona(
    name="Ana, se echa atrás",
    characteristics=(
        "Eres Ana García Ruiz, paciente de Clínica Norte, y llamas para cambiar tu cita de "
        f"traumatología. {VOICE} Eliges una de las horas que te ofrezcan, pero en cuanto te la "
        "lean para confirmarla te echas atrás: dices que no, que mejor lo dejas y ya llamarás "
        "otro día. No confirmas nada, pase lo que pase."
    ),
)

MOVED = "La cita queda cambiada a una hora nueva y el paciente lo sabe."
NOTHING_MOVED = "No se cambia nada y la cita que el paciente ya tenía sigue en pie."


def goldens() -> list[ConversationalGolden]:
    """The five calls to simulate: two that go smoothly, two that wobble, one that backs out."""
    return [
        ConversationalGolden(
            name="colaboradora-jueves",
            scenario="La paciente quiere mover su cita de traumatología al jueves.",
            expected_outcome=MOVED,
            persona=COOPERATIVE,
        ),
        ConversationalGolden(
            name="colaboradora-viernes",
            scenario="La paciente quiere mover su cita de traumatología al viernes.",
            expected_outcome=MOVED,
            persona=COOPERATIVE,
        ),
        ConversationalGolden(
            name="cambia-de-idea-jueves",
            scenario="La paciente pide el jueves, luego prefiere el viernes, y acaba en el jueves.",
            expected_outcome=MOVED,
            persona=CHANGES_MIND,
        ),
        ConversationalGolden(
            name="cambia-de-idea-viernes",
            scenario="La paciente pide el viernes, luego el jueves, y acaba en el viernes.",
            expected_outcome=MOVED,
            persona=CHANGES_MIND,
        ),
        ConversationalGolden(
            name="se-echa-atras",
            scenario="La paciente elige una hora del jueves y se echa atrás al confirmarla.",
            expected_outcome=NOTHING_MOVED,
            persona=BACKS_OUT,
        ),
    ]


def simulate_calls() -> list[ConversationalTestCase]:
    """Run every golden once and return the conversations as multi-turn cases, in that order."""
    caller = ReschedulingCaller()
    cards = goldens()
    simulator = ConversationSimulator(
        model_callback=caller.answer,
        simulator_model=AnthropicModel(model=SIMULATOR_MODEL),
        stopping_controller=stop_when_the_change_is_settled,
        language="Spanish",
        # One at a time: it keeps the calls in golden order (which is how they are paired
        # back up below) and five sessions talking to Anthropic at once buys nothing.
        max_concurrent=1,
    )
    loop = get_or_create_event_loop()
    try:
        simulator.simulate(cards, max_user_simulations=MAX_USER_TURNS)
    finally:
        loop.run_until_complete(caller.hang_up())
    return caller.cases(cards)


def stop_when_the_change_is_settled(last_assistant_turn: Turn | None) -> Decision:
    """End the call the moment the appointment is moved or refused — no judge, two tool names."""
    if last_assistant_turn is None:
        return proceed()
    called = {tool.name for tool in last_assistant_turn.tools_called or []}
    if BOOKED in called:
        return end("the appointment was moved")
    if DECLINED in called:
        return end("the patient did not confirm")
    return proceed()


class ReschedulingCaller:
    """The clinic's agent, as one live call per simulated conversation.

    DeepEval hands a callback one user line at a time and expects the
    assistant's answer back, with no notion of a session behind it. The
    `thread_id` it passes is the only thing that says which conversation a line
    belongs to, so it is what the open calls are keyed by.
    """

    def __init__(self) -> None:
        self._sessions = AsyncExitStack()
        self._calls: dict[str, LiveCall] = {}
        self._order: list[str] = []
        self._descriptions: dict[str, str] = {}

    async def answer(self, input: str, thread_id: str) -> Turn:
        """One line from the patient in, the stage's whole answer out, tools and all."""
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
        tc = identified_context()
        self._descriptions = self._descriptions or tool_descriptions(tc)
        call = await self._sessions.enter_async_context(live_conversation(tc, ChooseSlot(tc)))
        self._calls[thread_id] = call
        self._order.append(thread_id)
        return call


def identified_context() -> TenantContext:
    """A session that has already found Ana García's cita: exactly where ChooseSlot begins.

    `prev_agent` matters as much as `customer`. What ChooseSlot knows about the
    caller arrives as the previous stage's `summary()` in its `on_enter`, and a
    stage entered without one opens by asking for the name again — the right
    behaviour, and the wrong conversation to be simulating here.
    """
    tc = fake_context(TENANT, PROJECT)
    tc.customer = {"appointment_id": ANA, **tc.adapters["agenda"].book[ANA]}
    tc.prev_agent = Identify(tc)
    return tc
