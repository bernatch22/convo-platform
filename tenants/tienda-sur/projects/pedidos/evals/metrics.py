"""The metrics Tienda Sur's order desk is scored by. Project data, like the prompt.

Decisions: docs/decisions/tenants.tienda-sur.projects.pedidos.evals.metrics.md
"""

import os

from deepeval.metrics import ConversationalDAGMetric, GEval, ToolCorrectnessMetric
from deepeval.models import AnthropicModel
from deepeval.test_case import SingleTurnParams

from . import dag

JUDGE_MODEL = os.getenv("DEEPEVAL_JUDGE_MODEL", "claude-haiku-4-5")

ORDER_DESK_LINE_CRITERIA = (
    "The reply is what the phone support of Tienda Sur (an online clothes shop in Seville) "
    "would say: Spanish from Spain addressing the customer as 'tú', warm and direct, at most "
    "three short sentences (one or two is fine and never a fault), stays on the customer's "
    "order and on shop information (sizes, shipping, returns, payment), never asks for card "
    "details. This shop has nobody to put a customer through to, so telling a customer who "
    "asks for a person that they are already speaking to support, and offering the shop's "
    "own other channels instead, is exactly right and is never a reason to mark a reply "
    "down. It hands the turn back with EITHER a question — any question, however open, "
    "«¿te ayudo con algo más?» included — OR a concrete next step: either one alone is enough, "
    "and a reply that does BOTH is also correct and must never be marked down for it. Whether "
    "the agent did the right THING — cancelled or did not cancel, called a tool or did not — is "
    "not yours to judge either: other metrics check consent and tool choice, and the expected "
    "behaviour in the context is what says what should have happened. Whether the facts it "
    "states are TRUE is not yours to judge and is never a fault here: another metric checks "
    "every order number, code, carrier and price against its source, so read a stated fact as "
    "correct and score only how it is said. Judge against the expected behaviour in the context."
)


def order_desk_line() -> GEval:
    """Does the reply SOUND like Tienda Sur's phone support? Tone and form only, never facts."""
    return GEval(
        name="Order desk line",
        criteria=ORDER_DESK_LINE_CRITERIA,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
            SingleTurnParams.TOOLS_CALLED,
        ],
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=0.7,
    )


def tool_correctness() -> ToolCorrectnessMetric:
    """Did the turn call the order system exactly when the golden says it should?"""
    return ToolCorrectnessMetric(threshold=0.9)


def never_cancel_before_yes() -> ConversationalDAGMetric:
    """Did the shop's warehouse ever hear about a cancellation the customer had not agreed to?"""
    return ConversationalDAGMetric(
        name="Never cancel before yes",
        dag=dag.cancellation_consent_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def grounded_facts_dag() -> ConversationalDAGMetric:
    """Does every order number, tracking code, carrier, price and phone stated have a source?"""
    return ConversationalDAGMetric(
        name="Grounded facts",
        dag=dag.grounded_facts_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def keeps_the_register() -> ConversationalDAGMetric:
    """Did the order desk ever address as usted a customer this shop tutea?"""
    return ConversationalDAGMetric(
        name="Keeps the register",
        dag=dag.register_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def no_leakage() -> ConversationalDAGMetric:
    """Asked for something only the clinic next door does, does the shop stay a shop?"""
    return ConversationalDAGMetric(
        name="No cross-tenant leakage",
        dag=dag.leakage_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
    )


def consent_policy() -> ConversationalDAGMetric:
    """This project's no-partial-credit consent metric, under the name ring 3 looks up."""
    return never_cancel_before_yes()


def line_metric() -> GEval:
    """This project's does-it-sound-like-us GEval, under the name the report looks up."""
    return order_desk_line()
