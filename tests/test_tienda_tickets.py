"""The shop's incident desk: a number that outlives the call, and a write nobody has to consent to.

Two claims are worth a suite of their own, and neither needs a model.

The first is about IDENTITY. Every other fake system in this project answers
about something that existed before the phone rang, so its adapter records what
it changed and never reads it back. A ticket is the opposite: it comes into
being mid-call and its whole value is that the NEXT call — another room,
another job, another process — can find it by the number the customer wrote
down. So `FakeTickets` reads the ledger, and the test for it is two adapter
instances that never met.

The second is about CONSENT, and it is a cost claim as much as a policy one.
Opening an incident is a `write`: nothing left the shop, nothing was charged,
and a ticket opened by mistake is closed by the team that reads it. The
project's consent graph therefore has to score a ticket call 1.0 without asking
a judge anything at all, and the counting judge below is the only way to prove
"without asking" rather than merely "correctly".

No key, no network, milliseconds. `pytest -m unit`.
"""

import importlib
from typing import Any

import pytest
from deepeval.metrics import ConversationalDAGMetric
from deepeval.metrics.dag.schema import BinaryJudgementVerdict, TaskNodeOutput
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, ToolCall, Turn

from convo.adapters.base import LIST_RECORDS
from convo.domain import business
from convo.domain.tools import SideEffect
from convo.state.store import MemoryStore
from convo.testing import fake_context

pytestmark = pytest.mark.unit

TENANT, PROJECT = "tienda-sur", "pedidos"
PACKAGE = f"tenants.{TENANT}.projects.{PROJECT}"
project_module = importlib.import_module(f"{PACKAGE}.project")
stages = importlib.import_module(f"{PACKAGE}.stages")
helpers_module = importlib.import_module(f"{PACKAGE}.helpers")
messages_module = importlib.import_module(f"{PACKAGE}.messages")
evals_dag = importlib.import_module(f"{PACKAGE}.evals.dag")
tickets_module = importlib.import_module(f"tenants.{TENANT}.adapters.tickets")
ticketbook = importlib.import_module(f"tenants.{TENANT}.adapters.ticketbook")

IN_PROGRESS = "TS-T0001"  # Javier Nieto Salas: the parcel that says delivered and is not
RESOLVED = "TS-T0002"  # Lucía Ferrer Blanco: closed a week ago
PREPARING = "TS-10432"  # Marta Alonso Gil's order, still in the warehouse

HER_WORDS = "me ha llegado una sudadera con un agujero en la manga"


@pytest.fixture
def tc():
    """A session that has already found Marta's order, which is one way into TicketDesk."""
    context = fake_context(TENANT, PROJECT)
    context.customer = {"order_id": PREPARING, **context.adapters["orders"].book[PREPARING]}
    return context


class CountingJudge(DeepEvalBaseLLM):
    """A judge that answers whatever the test told it to and remembers every prompt it saw.

    The point of it is the length of `prompts`: a graph whose first node is
    computed makes no call at all, and nothing but a counter proves that.
    """

    def __init__(self) -> None:
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
        return BinaryJudgementVerdict(verdict=True, reason="the fake judge said so")

    async def a_generate(self, prompt: str, schema: Any = None, **kwargs) -> Any:
        """Same answer, no await: the fake does no I/O."""
        return self.generate(prompt, schema=schema, **kwargs)


def ticket_call(judge: CountingJudge) -> ConversationalDAGMetric:
    """The shop's own consent metric, in front of a fake judge instead of Haiku."""
    return ConversationalDAGMetric(
        name="Never cancel before yes",
        dag=evals_dag.cancellation_consent_graph(),
        model=judge,
        threshold=1.0,
        include_reason=False,
    )


# --- the helpdesk -----------------------------------------------------------


def test_a_ticket_number_is_found_however_the_customer_reads_it_out() -> None:
    """It is dictated over the phone and typed back on the next call, so it is read loosely."""
    book = ticketbook.seeded()

    assert ticketbook.lookup(book, "TS-T0001", None)["name"] == "Javier Nieto Salas"
    assert ticketbook.lookup(book, "ts t 1", None)["ticket_id"] == IN_PROGRESS
    assert ticketbook.lookup(book, "tst0002", None)["ticket_id"] == RESOLVED
    assert ticketbook.lookup(book, None, "600 666 777")["ticket_id"] == RESOLVED
    assert ticketbook.lookup(book, "TS-T9999", "699000000") is None


async def test_an_incident_opened_in_one_call_is_read_by_its_number_in_the_next() -> None:
    """The whole reason this adapter reads the ledger: a ticket outlives the call that opened it."""
    took_the_call = tickets_module.FakeTickets()
    opened = await took_the_call.execute(
        "open_ticket", {"subject": HER_WORDS, "phone": "600222333"}
    )

    rang_again = tickets_module.FakeTickets()  # another job, another process, the same helpdesk
    found = await rang_again.execute("ticket_status", {"ticket_id": opened["ticket_id"]})

    assert opened["ticket_id"] == "TS-T0003", "one past the two the shop already had"
    assert found["subject"] == HER_WORDS
    assert found["status"] == ticketbook.OPEN


async def test_two_incidents_opened_in_a_row_never_share_a_number() -> None:
    helpdesk = tickets_module.FakeTickets()

    first = await helpdesk.execute("open_ticket", {"subject": HER_WORDS})
    second = await helpdesk.execute("open_ticket", {"subject": "y además falta el pantalón"})

    assert [first["ticket_id"], second["ticket_id"]] == ["TS-T0003", "TS-T0004"]


async def test_the_subject_stored_is_the_customers_own_words_and_nothing_else() -> None:
    """What a stranger reads off the ticket has to be what the customer said, not our summary."""
    helpdesk = tickets_module.FakeTickets()

    opened = await helpdesk.execute(
        "open_ticket", {"subject": f"  {HER_WORDS}\n  ", "phone": "600222333"}
    )

    assert opened["subject"] == HER_WORDS
    assert opened["order_id"] == "", "no order was named, so none is invented"


async def test_an_incident_with_nothing_written_in_it_is_refused_by_the_helpdesk() -> None:
    with pytest.raises(ValueError, match="subject"):
        await tickets_module.FakeTickets().execute("open_ticket", {"subject": "   "})


def test_the_log_line_of_an_opened_ticket_carries_the_number_and_never_the_words() -> None:
    """`result_summary` is what the Board reads; a subject is whatever a person dictated."""
    line = tickets_module.summarise_ticket(
        {"ticket_id": "TS-T0003", "status": ticketbook.OPEN, "subject": HER_WORDS}
    )

    assert line == "ticket TS-T0003 abierto"
    assert "sudadera" not in line


# --- the contract -----------------------------------------------------------


def test_opening_an_incident_is_a_write_and_asks_nobody_for_a_second_yes() -> None:
    """The consent gate is for what cannot be undone; writing down a problem can."""
    catalog = project_module.PROJECT.tools

    assert catalog.get("open_ticket").side_effect is SideEffect.WRITE
    assert catalog.get("open_ticket").needs_confirmation() is False
    assert catalog.get("ticket_status").side_effect is SideEffect.READ
    assert [name for name in catalog.names() if catalog.get(name).needs_confirmation()] == [
        "cancel_order"
    ], "the shop still has exactly one irreversible door"


def test_the_free_text_a_customer_dictates_is_declared_as_pii() -> None:
    """A subject can hold an address, a neighbour's name, somebody else's order number."""
    spec = project_module.PROJECT.tools.get("open_ticket")

    assert spec.masks("subject")
    assert spec.masks("phone")


async def test_an_incident_carries_the_order_the_call_had_already_located(tc) -> None:
    """The customer does not repeat themselves: the located order travels into the ticket."""
    stage = stages.TicketDesk(tc)
    assert "Todavía no" in stage.summary()

    await tc.tools.call(
        "open_ticket",
        {
            "subject": HER_WORDS,
            "name": tc.customer["name"],
            "phone": tc.customer["phone"],
            "order_id": tc.customer["order_id"],
        },
    )
    rows = (await tc.adapters["tickets"].execute(LIST_RECORDS, {}))["rows"]
    opened = next(row for row in rows if row["id"] == "TS-T0003")

    assert opened["who"] == "Marta Alonso Gil"
    assert opened["detail"] == HER_WORDS
    assert opened["state"] == ticketbook.OPEN


def test_an_incident_nobody_can_find_is_said_so_plainly_and_offered_a_new_one() -> None:
    assert "no consta" in messages_module.NO_TICKET.lower()
    assert "abrirle una nueva" in messages_module.NO_TICKET


def test_the_line_read_back_names_the_number_the_state_and_what_was_written() -> None:
    ticket = {"ticket_id": IN_PROGRESS, **ticketbook.seeded()[IN_PROGRESS]}

    said = helpers_module.ticket_line(ticket)

    assert IN_PROGRESS in said
    assert "en curso" in said
    assert "entregado pero no lo ha recibido nadie" in said
    assert "TS-10433" in said, "the order it is about, because the helpdesk recorded one"


# --- the console ------------------------------------------------------------


async def test_the_shop_answers_two_tables_and_never_one_with_a_mixed_vocabulary() -> None:
    """Orders and incidents are different records: own shape, own columns, own state words."""
    from convo.session.registry import load_registry

    view = await business.records(load_registry()[TENANT], PROJECT, MemoryStore())

    shapes = [table["shape"] for table in view["views"]]
    tickets = next(table for table in view["views"] if table["shape"] == "tickets")

    assert shapes == ["orders", "tickets"], "in the order the tenant's factory builds them"
    assert view["shape"] == "orders", "the flat view is still the first, as it always was"
    assert tickets["labels"]["detail"] == "asunto"
    assert {row["state"] for row in tickets["rows"]} == {"en curso", "resuelto"}
    assert any(row["id"] == RESOLVED and row["tone"] == "gone" for row in tickets["rows"])


# --- the metric -------------------------------------------------------------


def test_a_call_that_only_opened_a_ticket_costs_the_consent_metric_no_judge_call() -> None:
    """A write is not an irreversible: the graph stops at its first, computed node."""
    judge = CountingJudge()
    metric = ticket_call(judge)
    case = ConversationalTestCase(
        turns=[
            Turn(role="user", content="es que ha llegado con un agujero"),
            Turn(
                role="assistant",
                content="Te la dejo apuntada con el número TS-T0003.",
                tools_called=[ToolCall(name="open_ticket")],
            ),
        ]
    )

    assert metric.measure(case) == 1.0
    assert judge.prompts == [], "nothing irreversible ran, so nothing was worth asking about"
