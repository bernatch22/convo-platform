"""Ten calls to the clinic nobody scripted: who calls, what should happen, where each starts.

The machinery is `core.testing.simulator` — one live session per conversation, a
deterministic stopping controller, one call at a time. What lives here is the
clinic's half of it, and only that: the personas, the goldens, the tool names
that settle a call, and the context each call starts from.

Three batches, because the clinic has three errands and a `SimulatedCaller`
opens every conversation at ONE stage. Five callers move a cita they already
have, three ask for a first one and two change the number the clinic rings them
on; the lists are concatenated in that order and `simulate_calls()` returns them
in the order `goldens()` names them, which is how a score is paired back to the
call that earned it.

Three of these choices are worth the sentence:

- **The rescheduling calls start at `ChooseSlot`, already identified.** Every
  user turn is a Haiku call for the persona and another for the agent, and
  identification is already pinned by `tests/test_stages.py` with two
  deterministic turns. Paying five conversations' worth of model time to
  re-prove it would buy nothing this metric can read: `book_slot` only exists in
  the stage these calls start in. The new-booking calls start at `NewBooking`
  for the same reason.
- **`book_slot`, `create_appointment`, `update_contact` and `decline` end the
  call.** The first three mean something irreversible was written, the last that
  the patient said no. None of them needs a judge.
- **The two who back out are the cheapest goldens here.** The consent graph's
  first node is computed, so a conversation where nothing was written ends
  there: they are scored on every model and in every nightly for nothing
  (`tests/test_consent_dag.py` counts the judge calls and gets zero, on the new
  door as on the old ones).
"""

from deepeval.dataset import ConversationalGolden, Persona
from deepeval.test_case import ConversationalTestCase

from core.context import TenantContext
from core.testing import fake_context
from core.testing.simulator import SimulatedCaller, settled_when

from ..stages import ChooseSlot, Identify, NewBooking, UpdateContact
from ..stages.identify import CONTACT

TENANT, PROJECT = "clinica-norte", "reagendamiento"
ANA = "ap-20260903-1000-trau"  # the seeded appointment every rescheduling call moves
PEDRO = {"patient": "Pedro Ramos Gil", "phone": "699000000"}  # nobody the book has held

MAX_USER_TURNS = 6
SETTLED = {
    "book_slot": "the appointment was moved",
    "decline": "the patient did not confirm",
}
NEW_BOOKING_SETTLED = {
    "create_appointment": "the appointment was created",
    "decline": "the patient did not confirm",
}
CONTACT_SETTLED = {
    "update_contact": "the contact number was changed",
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

NEW_VOICE = (
    "Hablas español de España, por teléfono, en frases cortas. Nunca escribes acotaciones ni "
    "describes lo que haces: dices tu frase y nada más. Ya has dado tu nombre y tu teléfono al "
    "empezar la llamada, así que no los repitas si no te los piden."
)

WANTS_ONE = Persona(
    name="Pedro, no tiene cita",
    characteristics=(
        "Eres Pedro Ramos Gil y llamas a Clínica Norte para pedir cita por primera vez: no "
        f"tienes ninguna. {NEW_VOICE} Dices para qué especialidad la quieres y qué día te "
        "viene bien, eliges una de las horas que te ofrezcan y, cuando te lean la hora entera "
        "y te pregunten si te la reservan, dices que sí con claridad."
    ),
)
WANTS_ONE_ANOTHER_DAY = Persona(
    name="Pedro, cambia de día",
    characteristics=(
        "Eres Pedro Ramos Gil y llamas a Clínica Norte para pedir cita por primera vez: no "
        f"tienes ninguna. {NEW_VOICE} Pides un día; cuando te ofrezcan horas, dices que ese "
        "día no puedes y pides otro. Después eliges una hora de las nuevas y, si te la leen "
        "para reservarla, dices que sí."
    ),
)
WANTS_ONE_THEN_DOESNT = Persona(
    name="Pedro, se echa atrás",
    characteristics=(
        "Eres Pedro Ramos Gil y llamas a Clínica Norte para pedir cita por primera vez: no "
        f"tienes ninguna. {NEW_VOICE} Eliges una de las horas que te ofrezcan, pero en cuanto "
        "te la lean para reservarla te echas atrás: dices que no, que lo consultas en casa y "
        "ya llamarás. No confirmas nada, pase lo que pase."
    ),
)

CONTACT_VOICE = (
    "Hablas español de España, por teléfono, en frases cortas. Nunca escribes acotaciones ni "
    "describes lo que haces: dices tu frase y nada más. Ya has dado tu nombre al empezar la "
    "llamada, así que no lo repitas si no te lo piden."
)

CHANGES_HER_NUMBER = Persona(
    name="Ana, cambia de teléfono",
    characteristics=(
        "Eres Ana García Ruiz, paciente de Clínica Norte, y llamas porque el teléfono que "
        f"tienen tuyo ya no es el tuyo. {CONTACT_VOICE} El que tenían acaba en 456 y lo "
        "reconoces en cuanto te lo digan. Tu número nuevo es el 689 000 111 y lo dices entero "
        "cuando te lo pidan. Cuando te lean el número nuevo y te pregunten si te lo cambian, "
        "dices que sí con claridad."
    ),
)
CHANGES_HER_MIND_ABOUT_IT = Persona(
    name="Ana, se echa atrás con el teléfono",
    characteristics=(
        "Eres Ana García Ruiz, paciente de Clínica Norte, y llamas porque el teléfono que "
        f"tienen tuyo ya no es el tuyo. {CONTACT_VOICE} El que tenían acaba en 456 y lo "
        "reconoces. Das como número nuevo el 689 000 111, pero en cuanto te lo lean para "
        "cambiarlo te echas atrás: dices que no, que mejor lo dejas, que lo consultas en casa "
        "y ya llamarás. No confirmas nada, pase lo que pase."
    ),
)

MOVED = "La cita queda cambiada a una hora nueva y el paciente lo sabe."
NOTHING_MOVED = "No se cambia nada y la cita que el paciente ya tenía sigue en pie."
CREATED = "El paciente se queda con una cita nueva apuntada y lo sabe."
NOTHING_CREATED = "No se apunta ninguna cita y el paciente se queda sin ninguna."
RECONTACTED = "La ficha del paciente queda con el teléfono nuevo y el paciente lo sabe."
NOTHING_CHANGED = "No se cambia ningún dato y en la ficha sigue el teléfono de siempre."


def goldens() -> list[ConversationalGolden]:
    """The ten calls to simulate: rescheduling, then new bookings, then contact changes."""
    return [*rescheduling_goldens(), *new_booking_goldens(), *contact_goldens()]


def rescheduling_goldens() -> list[ConversationalGolden]:
    """The five that move a cita: two straightforward, two that wobble, one that backs out."""
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


def new_booking_goldens() -> list[ConversationalGolden]:
    """The three that create one: a straightforward first cita, a change of day, a refusal."""
    return [
        ConversationalGolden(
            name="cita-nueva-jueves",
            scenario="El paciente no tiene ninguna cita y quiere una de traumatología el jueves.",
            expected_outcome=CREATED,
            persona=WANTS_ONE,
        ),
        ConversationalGolden(
            name="cita-nueva-cambia-de-dia",
            scenario="El paciente pide el jueves, dice que no puede y acaba pidiendo el viernes.",
            expected_outcome=CREATED,
            persona=WANTS_ONE_ANOTHER_DAY,
        ),
        ConversationalGolden(
            name="cita-nueva-se-echa-atras",
            scenario="El paciente elige una hora y se echa atrás cuando se la leen para reservar.",
            expected_outcome=NOTHING_CREATED,
            persona=WANTS_ONE_THEN_DOESNT,
        ),
    ]


def contact_goldens() -> list[ConversationalGolden]:
    """The two that change a phone number: one that goes through, one that backs out."""
    return [
        ConversationalGolden(
            name="telefono-nuevo",
            scenario="La paciente quiere cambiar el teléfono que la clínica tiene suyo.",
            expected_outcome=RECONTACTED,
            persona=CHANGES_HER_NUMBER,
        ),
        ConversationalGolden(
            name="telefono-se-echa-atras",
            scenario="La paciente da un teléfono nuevo y se echa atrás al confirmarlo.",
            expected_outcome=NOTHING_CHANGED,
            persona=CHANGES_HER_MIND_ABOUT_IT,
        ),
    ]


def simulate_calls() -> list[ConversationalTestCase]:
    """Run every golden once and return the conversations as multi-turn cases, in `goldens()` order.

    Three `SimulatedCaller` batches because a caller opens every conversation at
    one stage, and the three errands begin at three. The order is the
    concatenation of the three golden lists, which is the contract the suite
    pairs scores by.
    """
    moved = SimulatedCaller(
        rescheduling_goldens(),
        lambda golden: identified_context(),
        ChooseSlot,
        stop_when=settled_when(SETTLED),
        max_user_turns=MAX_USER_TURNS,
    ).simulate()
    created = SimulatedCaller(
        new_booking_goldens(),
        lambda golden: unknown_context(),
        NewBooking,
        stop_when=settled_when(NEW_BOOKING_SETTLED),
        max_user_turns=MAX_USER_TURNS,
    ).simulate()
    recontacted = SimulatedCaller(
        contact_goldens(),
        lambda golden: contact_context(),
        UpdateContact,
        stop_when=settled_when(CONTACT_SETTLED),
        max_user_turns=MAX_USER_TURNS,
    ).simulate()
    return [*moved, *created, *recontacted]


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


def contact_context() -> TenantContext:
    """A session that has found Ana's record for a DATA change: where UpdateContact begins.

    The same patient as `identified_context` and a different note across the
    handoff. `Identify.errand` is what makes the difference: set to CONTACT its
    `summary()` hands the next stage the phone number reduced to its last three
    digits, which is the whole safeguard of this errand and therefore the thing
    a simulated call has to be scored with in place.
    """
    tc = fake_context(TENANT, PROJECT)
    tc.customer = {"appointment_id": ANA, **tc.adapters["agenda"].book[ANA]}
    identify = Identify(tc)
    identify.errand = CONTACT
    tc.prev_agent = identify
    return tc


def unknown_context() -> TenantContext:
    """A session that has found no cita for the caller: exactly where NewBooking begins.

    The difference from `identified_context` is one absent key. `customer` here
    carries a name and a phone and no `appointment_id`, which is what `Identify`
    writes when a caller asks for a first cita — and what makes the previous
    stage's `summary()` say there is nothing on the book, the sentence NewBooking
    opens on.
    """
    tc = fake_context(TENANT, PROJECT)
    tc.customer = dict(PEDRO)
    tc.prev_agent = Identify(tc)
    return tc
