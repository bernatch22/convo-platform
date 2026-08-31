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

No key, no network, milliseconds. `pytest -m unit`.
"""

from typing import Any

import pytest
from deepeval.metrics import ConversationalDAGMetric
from deepeval.metrics.dag.schema import BinaryJudgementVerdict, TaskNodeOutput
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, ToolCall, Turn

from core.testing.dag import NOTHING_WAS_SAID, consent_graph, ran_at, said_before

pytestmark = pytest.mark.unit

BOOK_SLOT, BOOK_APPOINTMENT = "book_slot", "book_appointment"

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
