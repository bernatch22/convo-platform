"""Five rescheduling calls nobody scripted: who calls, what should happen, where the call starts.

The machinery is `core.testing.simulator` — one live session per conversation, a
deterministic stopping controller, one call at a time. What lives here is the
clinic's half of it, and only that: three personas, five goldens, the two tool
names that settle a rescheduling call, and the context a call starts from.

Two of those choices are worth the sentence:

- **The calls start at `ChooseSlot`, already identified.** Every user turn is a
  Haiku call for the persona and another for the agent, and identification is
  already pinned by `tests/test_stages.py` with two deterministic turns. Paying
  five conversations' worth of model time to re-prove it would buy nothing this
  metric can read: `book_slot` only exists in the stage these calls start in.
- **`book_slot` and `decline` end the call.** The first means the change went
  through, the second that the patient said no to it. Neither needs a judge.
"""

from deepeval.dataset import ConversationalGolden, Persona
from deepeval.test_case import ConversationalTestCase

from core.context import TenantContext
from core.testing import fake_context
from core.testing.simulator import SimulatedCaller, settled_when

from ..stages import ChooseSlot, Identify

TENANT, PROJECT = "clinica-norte", "reagendamiento"
ANA = "ap-20260903-1000-trau"  # the seeded appointment every simulated call reschedules

MAX_USER_TURNS = 6
SETTLED = {
    "book_slot": "the appointment was moved",
    "decline": "the patient did not confirm",
}

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
    return SimulatedCaller(
        goldens(),
        lambda golden: identified_context(),
        ChooseSlot,
        stop_when=settled_when(SETTLED),
        max_user_turns=MAX_USER_TURNS,
    ).simulate()


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
