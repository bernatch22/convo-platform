"""Fixtures and fakes shared by the consent tests."""

from typing import Any

from deepeval.metrics import ConversationalDAGMetric
from deepeval.metrics.dag.schema import BinaryJudgementVerdict, TaskNodeOutput
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, ToolCall, Turn

from convo.testing.metrics.dag import consent_graph

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
