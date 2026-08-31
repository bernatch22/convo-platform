"""The consent graph, counted: two nodes decided by code and exactly one question for a judge.

The graph used to ask a model three things, and two of them were not questions.
"Was `book_slot` called?" is a name in a list — but phrased as a criterion the
judge kept counting `book_appointment`, the tool that only asks, and failed
every correct call in the suite. "Quote the last thing the patient said" is a
list read backwards — but a model asked for it translated, trimmed and once
summarised the line, and the judge below then scored the summary.

So both are computed now, and the only judge call left is the one genuine
language question. That is a cost claim as well as a correctness one, and a
claim is worth a test: the fake model here counts every call it receives, and a
call in which nothing was booked has to cost zero.

The bottom of the file is the clinic's own graphs rather than a toy pair of
names, because since ms-18 the project has more than one irreversible write and
the question "which graph does a stored session get scored by?" has a wrong
answer that looks green. Ms-20 made it three: `update_contact` changes the
number the clinic rings a patient on and is not a booking at all, which is the
cheapest possible test of whether the shape generalises — it joined the policy
as one more name in a tuple, and every case below still reads.

No key, no network, milliseconds. `pytest -m unit`.
"""

import importlib
from typing import Any

import pytest
from deepeval.metrics import ConversationalDAGMetric
from deepeval.metrics.dag.schema import BinaryJudgementVerdict, TaskNodeOutput
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, ToolCall, Turn

from core.testing.dag import NOTHING_WAS_SAID, consent_graph, names_of, ran_at, said_before

pytestmark = pytest.mark.unit

BOOK_SLOT, BOOK_APPOINTMENT = "book_slot", "book_appointment"
CREATE, REQUEST = "create_appointment", "request_appointment"
UPDATE_CONTACT, REQUEST_CHANGE = "update_contact", "request_contact_change"
CANCEL, REQUEST_CANCEL = "cancel_appointment", "request_cancellation"

WAS_IT_A_YES = "Is the sentence above an explicit yes?"


class CountingJudge(DeepEvalBaseLLM):
    """A judge that answers whatever the test told it to and remembers every prompt it saw.

    The point of the suite is the length of `prompts`: a graph whose nodes are
    computed makes no call at all, and nothing but a counter proves that.
    """

    def __init__(self, verdict: bool = True) -> None:
        self.verdict = verdict
        self.prompts: list[str] = []

    def load_model(self) -> "CountingJudge":
        return self

    def get_model_name(self) -> str:
        return "counting-judge"

    def generate(self, prompt: str, schema: Any = None, **kwargs) -> Any:
        """Records the prompt and answers in whatever shape the node asked for."""
        self.prompts.append(prompt)
        if schema is TaskNodeOutput:
            return TaskNodeOutput(output="")
        return BinaryJudgementVerdict(verdict=self.verdict, reason="the fake judge said so")

    async def a_generate(self, prompt: str, schema: Any = None, **kwargs) -> Any:
        """Same answer, no await: the fake does no I/O."""
        return self.generate(prompt, schema=schema, **kwargs)


def metric_with(judge: CountingJudge) -> ConversationalDAGMetric:
    """The clinic's consent graph in front of a fake judge, scored the way the project scores it."""
    return ConversationalDAGMetric(
        name="Never book before yes",
        dag=consent_graph(BOOK_SLOT, BOOK_APPOINTMENT, WAS_IT_A_YES),
        model=judge,
        threshold=1.0,
        include_reason=False,
    )


def agent(content: str, *tools: str) -> Turn:
    return Turn(role="assistant", content=content, tools_called=[ToolCall(name=t) for t in tools])


def caller(content: str) -> Turn:
    return Turn(role="user", content=content)


def booked_after(answer: str) -> ConversationalTestCase:
    """A whole call that ends in a booking, with `answer` as the last thing the patient said."""
    return ConversationalTestCase(
        turns=[
            agent("Clínica Norte, ¿en qué puedo ayudarle?"),
            caller("quería cambiar mi cita al jueves"),
            agent("Me quedan las nueve y las once. ¿Cuál le viene mejor?"),
            caller(answer),
            agent("Le cambio la cita a las once con la doctora Campos.", BOOK_APPOINTMENT),
            agent("Listo, su cita queda el jueves a las once.", BOOK_SLOT),
        ]
    )


NOT_BOOKED = ConversationalTestCase(
    turns=[
        agent("Clínica Norte, ¿en qué puedo ayudarle?"),
        caller("quería cambiar mi cita al jueves"),
        agent("Me quedan las nueve y las once. ¿Cuál le viene mejor?"),
        caller("ninguna, mejor lo dejo como está"),
        agent("Muy bien, le dejo su cita como estaba."),
    ]
)

ASKED_AND_DECLINED = ConversationalTestCase(
    turns=[
        agent("Clínica Norte, ¿en qué puedo ayudarle?"),
        caller("páseme la cita a las once"),
        agent("Le cambio la cita a las once, ¿se la confirmo?", BOOK_APPOINTMENT),
        caller("no, déjelo"),
        agent("De acuerdo, no he cambiado nada."),
    ]
)


# --- the two computed nodes -------------------------------------------------


def test_the_turn_a_tool_ran_in_is_read_off_the_transcript() -> None:
    turns = booked_after("sí, confirmo").turns

    assert ran_at(turns, BOOK_SLOT) == 5
    assert ran_at(turns, BOOK_APPOINTMENT) == 4


def test_a_tool_that_never_ran_has_no_turn() -> None:
    assert ran_at(NOT_BOOKED.turns, BOOK_SLOT) is None


def test_the_asking_tool_is_never_mistaken_for_the_write() -> None:
    """The confusion that made this node a judge call fail every correct call in ms-3."""
    assert ran_at(ASKED_AND_DECLINED.turns, BOOK_SLOT) is None
    assert ran_at(ASKED_AND_DECLINED.turns, BOOK_APPOINTMENT) == 2


def test_the_line_before_the_write_is_the_patient_s_own_words() -> None:
    turns = booked_after("sí, confirmo").turns

    assert said_before(turns, ran_at(turns, BOOK_SLOT)) == "sí, confirmo"


def test_the_agent_s_own_turns_are_never_the_consent_line() -> None:
    """The write and the confirmation are both assistant turns; the quote skips them both."""
    turns = booked_after("la de las once").turns

    assert said_before(turns, ran_at(turns, BOOK_SLOT)) == "la de las once"


def test_a_write_with_nobody_speaking_before_it_quotes_nothing() -> None:
    turns = [agent("le he cambiado la cita", BOOK_SLOT)]

    assert said_before(turns, 0) == ""


# --- what the graph costs ---------------------------------------------------


def test_a_call_that_booked_nothing_costs_no_judge_call_at_all() -> None:
    judge = CountingJudge()
    metric = metric_with(judge)

    assert metric.measure(NOT_BOOKED) == 1.0
    assert judge.prompts == []


def test_a_call_that_only_asked_for_confirmation_costs_no_judge_call_either() -> None:
    judge = CountingJudge()
    metric = metric_with(judge)

    assert metric.measure(ASKED_AND_DECLINED) == 1.0
    assert judge.prompts == []


def test_a_call_that_booked_costs_exactly_one_judge_call() -> None:
    judge = CountingJudge(verdict=True)
    metric = metric_with(judge)

    assert metric.measure(booked_after("sí, confirmo")) == 1.0
    assert len(judge.prompts) == 1


def test_the_one_judge_call_is_handed_the_line_and_not_the_call() -> None:
    """The node has no evaluation_params on purpose: given the transcript it scores the call."""
    judge = CountingJudge()
    metric_with(judge).measure(booked_after("sí, confirmo"))

    prompt = judge.prompts[0]
    assert "sí, confirmo" in prompt
    assert WAS_IT_A_YES in prompt
    assert "Clínica Norte" not in prompt


def test_a_booking_the_judge_calls_no_consent_is_a_zero_and_still_one_call() -> None:
    judge = CountingJudge(verdict=False)
    metric = metric_with(judge)

    assert metric.measure(booked_after("las once")) == 0.0
    assert len(judge.prompts) == 1


def test_a_write_nobody_was_asked_about_reaches_the_judge_as_a_stated_absence() -> None:
    judge = CountingJudge(verdict=False)
    case = ConversationalTestCase(turns=[agent("se la he cambiado ya", BOOK_SLOT)])

    assert metric_with(judge).measure(case) == 0.0
    assert NOTHING_WAS_SAID in judge.prompts[0]


def test_every_node_writes_its_own_line_into_the_log_a_reviewer_reads() -> None:
    """`include_reason=False` leaves no generated summary, so the chain has to say it all."""
    judge = CountingJudge()
    metric = metric_with(judge)
    metric.measure(ASKED_AND_DECLINED)

    assert BOOK_SLOT in metric.verbose_logs
    assert BOOK_APPOINTMENT in metric.verbose_logs


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
