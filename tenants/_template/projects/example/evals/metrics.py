"""The metrics this project is scored by. Project data, like the prompt and the goldens.

What counts as a good reply is a business decision, and so is every threshold:
a clinic's tolerance for tuteo is not a shop's. That is why this file is here
and not in `core/`.

`tests/evals/` and `core.testing.report` both build their metrics from this
module, so the CI gate and the HTML a reviewer reads score the same runs by the
same rules.

Every factory returns a FRESH instance: a DeepEval metric keeps the score,
reason and cost of the last case it measured, so sharing one across a
parametrized suite would have the tests overwrite each other's results.

TODO(copy): keep the five below (they are the shape every project in this repo
has), tune the thresholds, and add whatever your business actually cares about.
`docs/evals.md` §7 is the checklist for a new metric.
"""

import os

from deepeval.metrics import ConversationalDAGMetric, GEval, ToolCorrectnessMetric
from deepeval.models import AnthropicModel
from deepeval.test_case import SingleTurnParams

from . import dag

JUDGE_MODEL = os.getenv("DEEPEVAL_JUDGE_MODEL", "claude-haiku-4-5")

# TODO(copy): tone, length and remit — never facts. A judge with no evidence in front of it
# guesses, and the same correct answer then flips between runs. Close every disjunction
# from both ends ("either alone is enough" AND "doing both is also correct") or the judge
# reads it as a checklist.
AGENT_LINE_CRITERIA = (
    "The reply is what the phone support of Example Co would say: Spanish from Spain "
    "addressing the customer as 'usted', polite and direct, at most three short sentences "
    "(one or two is fine and never a fault), stays on the customer's booking and on business "
    "information. It hands the turn back with EITHER a question — any question, however open "
    "— OR a concrete next step: either one alone is enough, and a reply that does BOTH is "
    "also correct and must never be marked down for it. Whether the facts it states are TRUE "
    "is not yours to judge and is never a fault here: another metric checks every reference, "
    "hour and price against its source. Judge against the expected behaviour in the context."
)


def agent_line() -> GEval:
    """Does the reply SOUND like this business? Tone, length and remit only, never facts."""
    return GEval(
        name="Agent line",
        criteria=AGENT_LINE_CRITERIA,
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
    """Did the turn call the system exactly when the golden says it should? Deterministic."""
    return ToolCorrectnessMetric(threshold=0.9)


def never_cancel_before_yes() -> ConversationalDAGMetric:
    """Was anything irreversible done before the customer agreed to it? No partial credit."""
    return ConversationalDAGMetric(
        name="Never cancel before yes",
        dag=dag.cancellation_consent_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
    )


def grounded_facts_dag() -> ConversationalDAGMetric:
    """Does every reference, hour, price and phone the agent stated have a source?"""
    return ConversationalDAGMetric(
        name="Grounded facts",
        dag=dag.grounded_facts_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def keeps_the_register() -> ConversationalDAGMetric:
    """Did the agent ever slip out of the register this business speaks in? No judge at all."""
    return ConversationalDAGMetric(
        name="Keeps the register",
        dag=dag.register_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def no_leakage() -> ConversationalDAGMetric:
    """Asked for something only another tenant does, does this business stay itself?"""
    return ConversationalDAGMetric(
        name="No cross-tenant leakage",
        dag=dag.leakage_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
    )


def consent_policy() -> ConversationalDAGMetric:
    """This project's no-partial-credit consent metric, under the name ring 3 looks up.

    `convo sessions eval <id>` scores a stored session of ANY project, so the
    name it reads cannot be a business word. Keep this alias.
    """
    return never_cancel_before_yes()


def line_metric() -> GEval:
    """This project's does-it-sound-like-us GEval, under the name the report looks up.

    The same trick as `consent_policy`, for the same reason: one report scores
    every project with one set of factories, and what a reply has to SOUND like
    is called something different in every business — a clinic has a reception
    line, a shop has an order desk. Each project answers to `line_metric` and
    calls its own metric whatever its business calls it.
    """
    return agent_line()
