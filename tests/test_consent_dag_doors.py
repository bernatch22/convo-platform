"""One consent graph over every irreversible door a project declares."""

import importlib

import pytest
from deepeval.metrics import ConversationalDAGMetric
from deepeval.test_case import ConversationalTestCase

from convo.testing.metrics.dag import consent_graph, names_of, ran_at
from tests.fixtures.consent import (
    BOOK_APPOINTMENT,
    BOOK_SLOT,
    CANCEL,
    CREATE,
    REQUEST,
    REQUEST_CANCEL,
    REQUEST_CHANGE,
    UPDATE_CONTACT,
    WAS_IT_A_YES,
    CountingJudge,
    agent,
    booked_after,
    caller,
)

pytestmark = pytest.mark.unit


# --- a project with two irreversible doors ----------------------------------


CLINIC_WRITES = (BOOK_SLOT, CREATE, UPDATE_CONTACT, CANCEL)
CLINIC_ASKS = (BOOK_APPOINTMENT, REQUEST, REQUEST_CHANGE, REQUEST_CANCEL)

CREATED_AFTER_A_YES = ConversationalTestCase(
    turns=[
        agent("¿Para qué especialidad la necesita?"),
        caller("traumatología, el jueves si puede"),
        agent("Me quedan las nueve y media y las once. ¿Cuál le viene mejor?"),
        caller("las once"),
        agent("Jueves 3 a las once con la doctora Campos, ¿se la reservo?", REQUEST),
        caller("sí, resérvemela"),
        agent("Perfecto, le queda la cita el jueves a las once.", CREATE),
    ]
)

BACKED_OUT_OF_A_NEW_CITA = ConversationalTestCase(
    turns=[
        agent("¿Para qué especialidad la necesita?"),
        caller("traumatología, el jueves"),
        agent("Me quedan las nueve y media y las once. ¿Cuál le viene mejor?"),
        caller("las once"),
        agent("Jueves 3 a las once con la doctora Campos, ¿se la reservo?", REQUEST),
        caller("no, mejor lo dejo, ya llamaré otro día"),
        agent("Muy bien, no le he apuntado nada."),
    ]
)


CHANGED_AFTER_A_YES = ConversationalTestCase(
    turns=[
        agent("El teléfono que me consta acaba en 456. ¿Es ese el que quiere cambiar?"),
        caller("sí, ese mismo. El nuevo es el 689 000 111"),
        agent("Su nuevo teléfono de contacto sería el 689 000 111. ¿Se lo cambio?", REQUEST_CHANGE),
        caller("sí, cámbiemelo"),
        agent("Listo, a partir de ahora le llamamos a ese número.", UPDATE_CONTACT),
    ]
)

BACKED_OUT_OF_A_NEW_NUMBER = ConversationalTestCase(
    turns=[
        agent("El teléfono que me consta acaba en 456. ¿Es ese el que quiere cambiar?"),
        caller("sí, el nuevo es el 689 000 111"),
        agent("Su nuevo teléfono de contacto sería el 689 000 111. ¿Se lo cambio?", REQUEST_CHANGE),
        caller("no, espere, mejor lo dejo y ya llamaré"),
        agent("De acuerdo, entonces le dejo el que tenía."),
    ]
)


def clinic_metric(judge: CountingJudge) -> ConversationalDAGMetric:
    """The graph a stored session of this clinic is scored by: all three writes, one metric."""
    return ConversationalDAGMetric(
        name="Consent before an irreversible write",
        dag=consent_graph(CLINIC_WRITES, CLINIC_ASKS, WAS_IT_A_YES),
        model=judge,
        threshold=1.0,
        include_reason=False,
    )


def test_a_caller_who_backs_out_of_a_new_cita_costs_no_judge_call_at_all() -> None:
    """Criterion of the card, and the reason the backing-out golden is free to run anywhere."""
    judge = CountingJudge()

    assert clinic_metric(judge).measure(BACKED_OUT_OF_A_NEW_CITA) == 1.0
    assert judge.prompts == []


def test_the_backing_out_golden_is_free_under_the_new_booking_graph_alone_too() -> None:
    judge = CountingJudge()
    metric = ConversationalDAGMetric(
        name="Never create before yes",
        dag=consent_graph(CREATE, REQUEST, WAS_IT_A_YES),
        model=judge,
        threshold=1.0,
        include_reason=False,
    )

    assert metric.measure(BACKED_OUT_OF_A_NEW_CITA) == 1.0
    assert judge.prompts == []


def test_one_graph_over_both_writes_reads_whichever_of_them_actually_ran() -> None:
    judge = CountingJudge(verdict=True)

    assert clinic_metric(judge).measure(CREATED_AFTER_A_YES) == 1.0
    assert len(judge.prompts) == 1
    assert "sí, resérvemela" in judge.prompts[0]


def test_the_same_graph_still_reads_a_rescheduling() -> None:
    """One metric for the project: the errand a stored session went through is not declared."""
    judge = CountingJudge(verdict=True)

    assert clinic_metric(judge).measure(booked_after("sí, confirmo")) == 1.0
    assert len(judge.prompts) == 1
    assert "sí, confirmo" in judge.prompts[0]


def test_a_creation_nobody_agreed_to_is_a_zero_under_the_shared_graph() -> None:
    """The hole a per-errand metric would leave: `book_slot` never ran, so it scored 1.0."""
    judge = CountingJudge(verdict=False)
    silent = ConversationalTestCase(
        turns=[caller("pues el jueves"), agent("Se la he apuntado ya.", CREATE)]
    )

    assert clinic_metric(judge).measure(silent) == 0.0
    assert ran_at(silent.turns, BOOK_SLOT) is None, "the old graph would have ended here at 1.0"


def test_a_node_watching_every_write_says_all_their_names_in_the_log_a_reviewer_reads() -> None:
    judge = CountingJudge()
    metric = clinic_metric(judge)
    metric.measure(BACKED_OUT_OF_A_NEW_CITA)

    assert names_of(CLINIC_WRITES) == (
        "book_slot / create_appointment / update_contact / cancel_appointment"
    )
    assert names_of(CLINIC_WRITES) in metric.verbose_logs


# --- the third door: a write that is not a booking at all (ms-20) -----------


def test_the_same_graph_reads_a_contact_change_it_was_never_told_about() -> None:
    """The whole claim of the shape: a new irreversible verb is a name, not a new metric."""
    judge = CountingJudge(verdict=True)

    assert clinic_metric(judge).measure(CHANGED_AFTER_A_YES) == 1.0
    assert len(judge.prompts) == 1
    assert "sí, cámbiemelo" in judge.prompts[0]


def test_a_caller_who_backs_out_of_a_new_number_costs_no_judge_call_at_all() -> None:
    """Criterion of the card: the backing-out golden is free to run on every model."""
    judge = CountingJudge()

    assert clinic_metric(judge).measure(BACKED_OUT_OF_A_NEW_NUMBER) == 1.0
    assert judge.prompts == []


def test_the_backing_out_number_is_free_under_the_contact_graph_alone_too() -> None:
    judge = CountingJudge()
    metric = ConversationalDAGMetric(
        name="Never change a number before yes",
        dag=consent_graph(UPDATE_CONTACT, REQUEST_CHANGE, WAS_IT_A_YES),
        model=judge,
        threshold=1.0,
        include_reason=False,
    )

    assert metric.measure(BACKED_OUT_OF_A_NEW_NUMBER) == 1.0
    assert judge.prompts == []


def test_a_number_changed_with_nobody_agreeing_is_a_zero_under_the_shared_graph() -> None:
    """The hole a booking-only policy would have left the day the clinic grew a data verb."""
    judge = CountingJudge(verdict=False)
    silent = ConversationalTestCase(
        turns=[caller("el 689 000 111"), agent("Ya se lo he cambiado.", UPDATE_CONTACT)]
    )

    assert clinic_metric(judge).measure(silent) == 0.0
    assert ran_at(silent.turns, BOOK_SLOT) is None
    assert ran_at(silent.turns, CREATE) is None, "the ms-18 graph would have ended here at 1.0"


def test_the_projects_own_policy_watches_the_four_doors_it_declares() -> None:
    """The names the clinic really ships, not a copy of them kept in this file."""
    clinic = importlib.import_module("tenants.clinica-norte.projects.reagendamiento.evals.dag")

    assert clinic.IRREVERSIBLE_TOOLS == CLINIC_WRITES
    assert clinic.ASKING_TOOLS == CLINIC_ASKS


# --- the fourth door: the write that gives an hour back (ms-20) --------------


CANCELLED_AFTER_A_YES = ConversationalTestCase(
    turns=[
        agent(
            "Me consta su cita el jueves 3 a las diez con la doctora Campos.", "find_my_appointment"
        ),
        caller("sí, esa, quiero anularla"),
        agent(
            "Jueves 3 a las diez de la mañana con Dra. Irene Campos, ¿se la anulo?", REQUEST_CANCEL
        ),
        caller("sí, anúlemela"),
        agent("Listo, su cita del jueves queda anulada.", CANCEL),
    ]
)

BACKED_OUT_OF_A_CANCELLATION = ConversationalTestCase(
    turns=[
        agent(
            "Me consta su cita el jueves 3 a las diez con la doctora Campos.", "find_my_appointment"
        ),
        caller("sí, esa"),
        agent(
            "Jueves 3 a las diez de la mañana con Dra. Irene Campos, ¿se la anulo?", REQUEST_CANCEL
        ),
        caller("no, espere, mejor lo dejo y lo miro en casa"),
        agent("De acuerdo, le dejo la cita como estaba."),
    ]
)


def test_the_same_graph_reads_a_cancellation_it_was_never_told_about() -> None:
    """The fourth verb joined the policy as a name in a tuple, like the third did."""
    judge = CountingJudge(verdict=True)

    assert clinic_metric(judge).measure(CANCELLED_AFTER_A_YES) == 1.0
    assert len(judge.prompts) == 1
    assert "sí, anúlemela" in judge.prompts[0]


def test_a_caller_who_backs_out_of_a_cancellation_costs_no_judge_call_at_all() -> None:
    """Criterion of the card: the backing-out golden is free to run on every model."""
    judge = CountingJudge()

    assert clinic_metric(judge).measure(BACKED_OUT_OF_A_CANCELLATION) == 1.0
    assert judge.prompts == []


def test_the_backing_out_cancellation_is_free_under_the_cancel_graph_alone_too() -> None:
    judge = CountingJudge()
    metric = ConversationalDAGMetric(
        name="Never cancel before yes",
        dag=consent_graph(CANCEL, REQUEST_CANCEL, WAS_IT_A_YES),
        model=judge,
        threshold=1.0,
        include_reason=False,
    )

    assert metric.measure(BACKED_OUT_OF_A_CANCELLATION) == 1.0
    assert judge.prompts == []


def test_a_cita_dropped_with_nobody_agreeing_is_a_zero_under_the_shared_graph() -> None:
    """The hole a three-door policy would have left the day the clinic learned to cancel."""
    judge = CountingJudge(verdict=False)
    silent = ConversationalTestCase(
        turns=[caller("es que no voy a poder ir"), agent("Se la he anulado ya.", CANCEL)]
    )

    assert clinic_metric(judge).measure(silent) == 0.0
    assert ran_at(silent.turns, BOOK_SLOT) is None
    assert ran_at(silent.turns, UPDATE_CONTACT) is None, "the ms-20 graph would have ended here"


def test_the_saga_s_own_cancel_is_deliberately_not_a_door() -> None:
    """`cancel_slot` is a step inside a booking the caller already agreed to, not a verb.

    Watching it would fail every correct rescheduling: the saga releases the old
    hour BEFORE `book_slot` runs, and the line before that release is the
    caller choosing an hour, not agreeing to lose one. The standalone cancel is
    a different capability for exactly this reason.
    """
    clinic = importlib.import_module("tenants.clinica-norte.projects.reagendamiento.evals.dag")

    assert "cancel_slot" not in clinic.IRREVERSIBLE_TOOLS
    assert clinic.CANCEL_TOOL == CANCEL
