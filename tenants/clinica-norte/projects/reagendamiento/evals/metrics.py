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

from deepeval.metrics import (
    ArgumentCorrectnessMetric,
    ConversationalDAGMetric,
    GEval,
    ToolCorrectnessMetric,
)
from deepeval.models import AnthropicModel
from deepeval.test_case import SingleTurnParams

from . import dag

JUDGE_MODEL = os.getenv("DEEPEVAL_JUDGE_MODEL", "claude-haiku-4-5")

RECEPTION_LINE_CRITERIA = (
    "The reply is what a phone receptionist of Clínica Norte (Madrid) would say: "
    "Spanish from Spain using 'usted', polite and warm, at most three short sentences "
    "(one or two is fine and never a fault), stays on appointments and clinic information, "
    "gives no clinical advice. It hands the turn back with EITHER a question — any question, "
    "however open, «¿qué necesita?» included — OR a concrete next step: either one alone is "
    "enough, and a reply that does BOTH is also correct and must never be marked down for it. "
    "Whether the facts it states are TRUE is not yours to judge and is never a fault here: "
    "another metric checks every hour, price and name against its source, so read a stated "
    "fact as correct and score only how it is said. Judge against the expected behaviour in "
    "the context."
)


def reception_line() -> GEval:
    """Does the reply SOUND like Clínica Norte's reception? Tone and form only, never facts.

    This metric used to own the invention rule too, and it could not hold it.
    A GEval turns its criteria into evaluation steps, and a step keeps only the
    clause it grew from, so "an hour needs a tool behind it" survived its own
    exception and failed the price answer for quoting 90 euros with nothing
    called — intermittently, 0.0 on one run and 0.9 on the next, because a
    judge with no evidence in front of it is guessing. Rewriting the sentence
    bought a week each time. The rule now lives in `grounded_facts_dag`, where
    code does the matching and the judge is only ever handed a claim and the
    document that does or does not contain it. What is left here is tone,
    register, length and remit — the things a judge is actually good at.

    Every either/or is still spelled out as "one alone is enough". Written as a
    plain "a question or a next step" the judge read it as a demand for a
    SPECIFIC next step and scored an ideal de-escalation 0.5 for ending on
    "¿qué necesita?". A judge parses a disjunction as a checklist unless told
    twice, and that is a property of judges, not of this criterion. Ms-5 found
    the same sentence still open at the other end: told only that both were
    "never required", the judge read an exclusive or and scored 0.6 for a reply
    that gave the price AND asked for the name. It now says both halves, in the
    same words the shop's criteria uses.

    The tools called stay in the evaluation params: several goldens describe a
    turn that must not consult the agenda, and a judge that cannot see whether
    it did has to guess at that too.
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


def never_book_before_yes() -> ConversationalDAGMetric:
    """Did the clinic's agenda ever hear about a change the patient had not agreed to?

    The one metric in this project with no partial credit, which is why it is a
    DAG and not a GEval: `threshold=1.0` and the graph only ever scores 1.0 or
    0.0, so "mostly asked for consent" is a failure and reads like one. The
    graph, the wording of each node and why the metric watches `book_slot`
    rather than `book_appointment` are all in `dag.py`.

    `include_reason=False` for the same reason as `grounded_facts_dag`: the two
    first nodes are computed, so a call in which nothing was booked costs zero
    model calls — and DeepEval's generated summary would be the only one left.
    Each node writes its own line into `verbose_logs` instead.
    """
    return ConversationalDAGMetric(
        name="Never book before yes",
        dag=dag.booking_consent_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def grounded_facts_dag() -> ConversationalDAGMetric:
    """Does every hour, price, name, phone and address the agent stated have a source?

    The evidence-gated pattern, and the reason this is a DAG and not a GEval:
    code extracts the claims and matches them against the clinic's sheet, what
    the caller said and what the tools returned, and only what survives that is
    shown to a judge — one binary question, with the evidence attached. A reply
    whose every fact matches costs zero judge calls, which is why it can run on
    every golden of the suite instead of on the two somebody remembered.

    `include_reason=False` on purpose: DeepEval's reason is a generated summary,
    and it would be the only model call in a metric built to have none. Every
    node writes its own one-line reason into `verbose_logs` instead — run the
    suite with `-v` (or `verbose_mode=True`) to read which claim was left over.
    """
    return ConversationalDAGMetric(
        name="Grounded facts",
        dag=dag.grounded_facts_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def keeps_the_register() -> ConversationalDAGMetric:
    """Did reception ever tutear a patient it has been addressing as usted?

    No judge at all: the graph is one deterministic node over a list of tú-forms
    (`dag.TU_FORMS`). It exists because a GEval asked about tone scored an
    otherwise good reply 0.8 and moved on, while for a clinic a single "¿cuál te
    viene mejor?" in a call that has been usted throughout sounds like another
    person picking up the phone. A rule a word list can decide is not a judge's
    to weigh.
    """
    return ConversationalDAGMetric(
        name="Keeps the register",
        dag=dag.register_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
        include_reason=False,
    )


def no_leakage() -> ConversationalDAGMetric:
    """Asked where a parcel is, does the clinic stay a clinic?

    The shop next door runs on the same worker, the same registry and the same
    session code; the only thing that keeps its carriers and its order numbers
    out of this call is that the context was built from this project's data.
    That is a claim about the runtime, so it is measured and not asserted in a
    docstring. Word list and criterion in `dag.py`, graph in
    `core.testing.leakage`.

    `threshold=1.0`: naming another business, or pretending to track anything,
    has no partial credit.
    """
    return ConversationalDAGMetric(
        name="No cross-tenant leakage",
        dag=dag.leakage_graph(),
        model=AnthropicModel(model=JUDGE_MODEL),
        threshold=1.0,
    )


def consent_policy() -> ConversationalDAGMetric:
    """This project's no-partial-credit consent metric, under the name ring 3 looks up.

    `convo sessions eval <id>` scores a stored session of ANY project, so the
    name it reads cannot be a clinic word: what a shop does irreversibly is
    cancel an order, not book an hour. Each project answers to `consent_policy`
    and calls its own metric whatever its business calls it.
    """
    return never_book_before_yes()
