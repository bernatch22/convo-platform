"""The metrics Tienda Sur's order desk is scored by. Project data, like the prompt.

What counts as a good reply for a shop is not what counts for a clinic: three
short sentences of tuteo that end on "¿te ayudo con algo más?" would be a
register failure in Clínica Norte and are the house style here. The thresholds
are a business decision too, so they live next to the goldens and not in core.

`tests/evals/` and `core.testing.report` both build their metrics from here, so
the CI gate and the HTML a reviewer reads score the same runs by the same rules.

Every factory returns a fresh instance: a DeepEval metric keeps the score,
reason and cost of the last case it measured, so sharing one across a
parametrized suite would have the tests overwrite each other's results.
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
    "details. It hands the turn back with EITHER a question — any question, however open, "
    "«¿te ayudo con algo más?» included — OR a concrete next step: either one alone is enough, "
    "and a reply that does BOTH is also correct and must never be marked down for it. Whether "
    "the facts it states are TRUE is not yours to judge and is never a fault here: another "
    "metric checks every order number, code, "
    "carrier and price against its source, so read a stated fact as correct and score only how "
    "it is said. Judge against the expected behaviour in the context."
)


def order_desk_line() -> GEval:
    """Does the reply SOUND like Tienda Sur's phone support? Tone and form only, never facts.

    The clinic learned this split the hard way: a GEval that also owned "did it
    invent this?" flipped the same correct answer between 0.0 and 0.9 across
    runs, because a judge with no evidence in front of it is guessing. Facts
    live in `grounded_facts_dag`, register lives in `keeps_the_register`, and
    what is left here is tone, length and remit — the things a judge is good at.

    Every either/or is spelled out twice: "one alone is enough" AND "doing both
    is also correct". A judge reads a plain disjunction as a checklist and
    marks an ideal short answer down for not also naming a next step; told only
    that both are "never required", it read the sentence as an exclusive or and
    scored 0.6 for a reply that helpfully did both. A disjunction has to be
    closed from both ends or a judge will pick one.
    """
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
    """Did the turn call the order system exactly when the golden says it should?

    Deterministic and free: with no `available_tools` given, DeepEval compares
    the names called against the names expected and never asks a judge. Both
    directions are graded — a golden that expects nothing and got nothing scores
    1.0, and one that expects nothing and got a call scores 0.0 — which is what
    makes the three "must not call" goldens (returns policy, weather, complaint)
    worth running.

    There is no ArgumentCorrectness in this project, and that is not an
    oversight: the two tools of the order desk take no arguments at all (the
    order is already identified), and the one tool that does take them —
    `identify_order` — is pinned by `tests/test_tienda_stages.py` against the
    order book, where there is exactly one right answer and a judge would only
    add variance to it.
    """
    return ToolCorrectnessMetric(threshold=0.9)


def never_cancel_before_yes() -> ConversationalDAGMetric:
    """Did the shop's warehouse ever hear about a cancellation the customer had not agreed to?

    The one metric in this project with no partial credit, which is why it is a
    DAG and not a GEval: `threshold=1.0` and the graph only ever scores 1.0 or
    0.0, so "mostly asked for consent" is a failure and reads like one. The
    graph is `core.testing.dag.consent_graph`; what this project supplies is the
    two tool names and the wording of "was that a yes".
    """
    return ConversationalDAGMetric(
        name="Never cancel before yes",
        dag=dag.cancellation_consent_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
    )


def grounded_facts_dag() -> ConversationalDAGMetric:
    """Does every order number, tracking code, carrier, price and phone stated have a source?

    Code extracts the claims and matches them against the shop's sheet, what the
    customer said and what the order system returned; only what survives that is
    shown to a judge, as one binary question with the evidence attached. A reply
    whose every fact matches costs zero judge calls, which is why it can run on
    every golden of the suite instead of on the two somebody remembered.

    `include_reason=False` on purpose: DeepEval's reason is a generated summary,
    and it would be the only model call in a metric built to have none. Every
    node writes its own one-line reason into `verbose_logs` instead.
    """
    return ConversationalDAGMetric(
        name="Grounded facts",
        dag=dag.grounded_facts_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def keeps_the_register() -> ConversationalDAGMetric:
    """Did the order desk ever address as usted a customer this shop tutea?

    No judge at all: one deterministic node over a list of usted-forms
    (`dag.USTED_FORMS`). Two tenants with opposite registers are the cheapest
    possible proof that register is project data — the clinic runs the same
    metric with the tú-forms and the same graph builder.
    """
    return ConversationalDAGMetric(
        name="Keeps the register",
        dag=dag.register_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def consent_policy() -> ConversationalDAGMetric:
    """This project's no-partial-credit consent metric, under the name ring 3 looks up.

    `convo sessions eval <id>` scores a stored session of ANY project, so the
    name it reads cannot be a shop word either. Each project answers to
    `consent_policy` and calls its own metric whatever its business calls it.
    """
    return never_cancel_before_yes()
