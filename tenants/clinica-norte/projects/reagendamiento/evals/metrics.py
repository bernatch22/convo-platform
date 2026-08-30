"""The metrics Clínica Norte's reception is scored by. Project data, like the prompt.

One small explicit list, in the project folder next to its goldens: what counts
as a good reply for a clinic's reception ("usted", two or three sentences, never
invents an hour) is not what counts for a shop's returns desk, and a threshold
is a business decision, not a platform default. `tests/evals/` and
`core.testing.report` both build their metrics from here, so the CI gate and the
HTML a reviewer reads score the same runs by the same rules.

Every factory returns a fresh instance: a DeepEval metric keeps the score,
reason and cost of the last case it measured, so sharing one across a
parametrized suite would have the tests overwrite each other's results.
"""

import os

from deepeval.metrics import ArgumentCorrectnessMetric, GEval, ToolCorrectnessMetric
from deepeval.models import AnthropicModel
from deepeval.test_case import SingleTurnParams

JUDGE_MODEL = os.getenv("DEEPEVAL_JUDGE_MODEL", "claude-haiku-4-5")

RECEPTION_LINE_CRITERIA = (
    "The reply is what a phone receptionist of Clínica Norte (Madrid) would say: "
    "Spanish from Spain using 'usted', polite and warm, at most three short sentences "
    "(one or two is fine and never a fault), stays on appointments and clinic information, "
    "gives no clinical advice. It hands the turn back with EITHER a question — any question, "
    "however open, «¿qué necesita?» included — OR a concrete next step: either one alone is "
    "enough and both together are never required. Exactly two kinds of claim need a tool "
    "behind them — a specific appointment hour, and the doctor attached to a specific slot — "
    "and they count as invented only when no tool output of this turn contains them, so read "
    "the tools called before deciding; nothing else needs a tool, and in particular prices, "
    "address, opening hours, the cancellation policy and how to prepare for a test are on the "
    "clinic's own information sheet, which the receptionist has in front of her, so stating "
    "any of them with no tool called is correct and is never an invention. Judge against the "
    "expected behaviour in the context."
)


def reception_line() -> GEval:
    """Does the reply sound like Clínica Norte's reception and stay within its remit?

    The tools called are part of what is judged, not decoration. Shown only the
    words, this judge scored two correct answers 0.6 and 0.2 for "inventing
    availability" — the hours were real, read off the agenda a line earlier,
    and the judge had no way to know. A metric that cannot see the evidence
    fails the agent for the metric's own blind spot.

    Every either/or in the criteria is spelled out as "one alone is enough".
    Written as a plain "a question or a next step" the judge read it as a
    demand for a SPECIFIC next step and scored an ideal de-escalation 0.5 for
    ending on "¿qué necesita?". A judge parses a disjunction as a checklist
    unless told twice, and that is a property of judges, not of this criterion.

    For the same reason the tool rule and its exception are ONE sentence. GEval
    turns criteria into evaluation steps, and a step keeps only the clause it
    grew from: split across two sentences, "hours need a tool" became a step of
    its own and failed the price answer for quoting 90 euros with nothing
    called — twice, intermittently, which is how a step that lost its exception
    behaves.
    """
    return GEval(
        name="Reception line",
        criteria=RECEPTION_LINE_CRITERIA,
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
    """Did the turn call the agenda exactly when the golden says it should?

    Deterministic and free: with no `available_tools` given, DeepEval compares
    the names called against the names expected and never asks a judge. Both
    directions are graded — a golden that expects nothing and got nothing
    scores 1.0, and one that expects nothing and got a call scores 0.0 — which
    is what makes the three "must not call" goldens worth running.

    Neither `should_exact_match` nor `should_consider_ordering` is set. Calling
    the agenda twice for one question (the patient named a day and a specialty)
    is not a defect worth failing a build over; calling it for a price question
    is, and the default scoring already says so.
    """
    return ToolCorrectnessMetric(threshold=0.9)


def argument_correctness() -> ArgumentCorrectnessMetric:
    """Do the arguments the model passed match what the patient actually asked for?

    Judged, not compared: the tool takes the day in the caller's own words, so
    "el jueves", "este jueves" and "2026-09-03" are all correct for the same
    question and no literal expected value could accept the three. The suite
    pins the resolved date separately, with `dates.resolve`; this metric is
    what catches a specialty invented or a day quietly swapped.

    It only works if the call carries the tool's description — the bridge puts
    it there. Without it the judge scored `date="el jueves"` 0.0, reasoning
    that the tool "requires YYYY-MM-DD": a contract it made up, and the exact
    opposite of what the docstring the model reads asks for.
    """
    return ArgumentCorrectnessMetric(threshold=0.8, model=AnthropicModel(model=JUDGE_MODEL))
