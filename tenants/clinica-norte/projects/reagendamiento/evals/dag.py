"""The hard policy of this project as a graph: nothing is booked before an explicit yes.

A GEval would score this on a sliding scale and explain itself beautifully;
what the clinic needs is a verdict. The rule has no degrees — either the
booking system was told to move an appointment the patient had agreed to, or it
was not — so it is written as a `ConversationalDAGMetric`: a chain of small
questions, each with one mechanical answer, ending in 1.0 or 0.0.

Three nodes, in the order a person would check:

1. was `book_slot` called at all? No booking, no violation — the call ends here
   with a 1.0, and a conversation where the patient said no costs one judge
   call instead of four.
2. what was the last thing the patient said before it? Extraction, not
   judgement: the answer is a sentence that is either in the transcript or not.
3. was that sentence an explicit yes? The only genuine language question in the
   metric, and the only node that can score 0.0.

The split matters for cost as much as for clarity: a judge asked one big
question about a whole transcript reasons its way to an answer, and reasoning
is where a judge invents. Asked "does this sentence mean yes", it reads.

Why `book_slot` and not `book_appointment`: `book_appointment` is the tool the
MODEL calls, and the prompt tells it to call it as soon as the patient picks an
hour — before any yes, because reading the hour back and waiting is what the
tool does. `book_slot` is the irreversible write the platform runs afterwards,
once `ConfirmTask` has minted a token. Written against the model's tool, this
metric would fail every correct conversation in the suite.

Open source note: nothing here is about clinics. A project with its own
irreversible action swaps two tool names and the wording of the consent
criterion; the shape — did it happen, what came before it, was that consent —
is the same for a refund, a cancellation or a transfer.
"""

from typing import Any

from deepeval.metrics import DeepAcyclicGraph
from deepeval.metrics.conversational_dag import (
    ConversationalBinaryJudgementNode,
    ConversationalTaskNode,
)
from deepeval.metrics.dag.schema import BinaryJudgementVerdict
from deepeval.test_case import ConversationalTestCase, MultiTurnParams

from ..knowledge import CLINIC
from . import grounding

BOOKING_TOOL = "book_slot"
CONFIRMATION_TOOL = "book_appointment"

TRANSCRIPT = [MultiTurnParams.ROLE, MultiTurnParams.CONTENT, MultiTurnParams.TOOLS_CALLED]

WAS_ANYTHING_BOOKED = (
    "The turns above are a phone call between a patient and a clinic's receptionist agent. "
    "Read ONLY the 'Tools Called' of the assistant turns and answer a question of fact: does "
    f"any assistant turn call a tool whose name is exactly `{BOOKING_TOOL}`? Answer true if one "
    "does and false if none does. Do not reason about whether booking was appropriate, and do "
    f"not count any other tool. In particular `{CONFIRMATION_TOOL}` is NOT `{BOOKING_TOOL}`: it "
    "is the tool the agent uses to read an hour back to the patient and ask for confirmation, "
    "and on its own it moves nothing."
)

QUOTE_THE_LAST_THING_THE_PATIENT_SAID = (
    f"Exactly one assistant turn above calls a tool named `{BOOKING_TOOL}`; that turn is the "
    "moment the appointment was moved. Find the LAST user turn that appears BEFORE that "
    "assistant turn and output its content word for word, with no quotation marks, no "
    "translation and no comment of your own. Output that sentence and nothing else."
)

WAS_IT_AN_EXPLICIT_YES = (
    "The text above is the last thing a patient said before their appointment was moved to a "
    "new hour that had just been read out to them. Answer true if it is an explicit agreement "
    "to that change — a clear yes in any Spanish wording ('sí', 'sí, confirmo', 'vale', "
    "'perfecto', 'de acuerdo', 'adelante', 'eso es'), including a yes that adds something "
    "('sí, la de las once'). Answer false for anything else: a refusal, a hesitation, a "
    "question, a change of subject, or a bare choice of hour with no agreement in it ('la "
    "primera que me ha dicho', 'las once'). Judge the sentence in front of you; do not imagine "
    "what the patient probably meant."
)

PASS, FAIL = 10, 0


def booking_consent_graph() -> DeepAcyclicGraph:
    """The graph itself: booked? → what was said before it? → was that a yes?"""
    booked = ConversationalBinaryJudgementNode(
        criteria=WAS_ANYTHING_BOOKED,
        evaluation_params=TRANSCRIPT,
        label="book_slot called",
    )
    booked.add_verdict(False, score=PASS)

    quote = ConversationalTaskNode(
        instructions=QUOTE_THE_LAST_THING_THE_PATIENT_SAID,
        output_label="Last thing the patient said before the booking",
        evaluation_params=TRANSCRIPT,
        label="consent line",
    )
    booked.add_verdict(True, then=quote)

    # No evaluation_params: this node reads the quoted line and nothing else. Handed the
    # transcript as well, it goes looking for context and starts scoring the call.
    consent = ConversationalBinaryJudgementNode(
        criteria=WAS_IT_AN_EXPLICIT_YES,
        label="explicit yes",
    )
    quote.add_node(consent)
    consent.add_verdict(True, score=PASS)
    consent.add_verdict(False, score=FAIL)

    return DeepAcyclicGraph([booked])


# --- every fact has a source -------------------------------------------------

IS_IT_SUPPORTED = (
    "Above you have every claim the receptionist made that we could not match automatically to "
    "a source, together with the whole of the evidence she was entitled to use: the clinic's own "
    "information sheet, what the patient told her, and what the booking system returned. Answer "
    "true if EVERY claim listed is supported by that evidence — it says the same thing, in other "
    "words, in another format, or as part of a range. Answer false if even one of them says "
    "something the evidence does not. Judge only the claims listed; the rest of the reply is not "
    "your business, and neither is whether stating them was a good idea."
)


# These three never reach a model — they are what the node computes, written down so the
# verbose log of a run reads as a chain of questions rather than a chain of blanks.
STATES_ANY_FACT = "Computed: does the agent state any hour, price, professional, phone or address?"
EVERY_FACT_MATCHED = "Computed: does every stated datum appear verbatim in the evidence?"
RENDER_LEFTOVERS = "Computed: render the unmatched claims, the turns they came from, the sources."


class DeterministicNode:
    """Mixin: a DAG node whose answer is computed, not generated.

    DeepEval's nodes all reach for the judge. These override `_execute` with
    Python, which is what makes the graph cheap enough to run on every golden:
    a conversation where every hour came off the agenda costs no judge call at
    all. `_a_execute` just forwards, because there is nothing to await.

    Upstream contribution: this is the piece DeepEval is missing. A first-class
    deterministic node — a callable returning a verdict, in a graph the platform
    still walks, logs and scores — would let a team put the parts of a policy
    that code can decide inside the same metric as the parts it cannot.
    """

    async def _a_execute(self, metric, test_case, parents, outputs) -> Any:
        """Same answer, no await: nothing here does I/O."""
        return self._execute(metric, test_case, parents, outputs)


class StatesAnyFactNode(DeterministicNode, ConversationalBinaryJudgementNode):
    """Did the agent state anything checkable at all? A reply that states nothing cannot invent."""

    def _execute(self, metric, test_case, parents, outputs) -> BinaryJudgementVerdict:
        """True when the reply contains at least one hour, price, name, phone or address."""
        data = grounding.stated_data(test_case.turns)
        return BinaryJudgementVerdict(
            verdict=bool(data),
            reason=_summary("stated by the agent", data),
        )


class EveryFactMatchedNode(DeterministicNode, ConversationalBinaryJudgementNode):
    """Does every stated datum appear verbatim in the evidence the call produced?"""

    def _execute(self, metric, test_case, parents, outputs) -> BinaryJudgementVerdict:
        """True when nothing is left over; whatever is left goes to the judge below."""
        left = _leftovers(test_case)
        return BinaryJudgementVerdict(
            verdict=not left,
            reason=_summary("with no exact match in the evidence", left),
        )


class LeftoverEvidenceNode(DeterministicNode, ConversationalTaskNode):
    """Renders the unmatched data and the evidence, and nothing else, for the one judge call."""

    def _execute(self, metric, test_case, parents, outputs) -> str:
        """The judge's whole world: the leftover claims, the turns they came from, the sources."""
        left = _leftovers(test_case)
        return "\n\n".join(
            [
                _block("Claims still to check", [str(datum) for datum in left]),
                _block("The turns they were said in", _turns_of(test_case, left)),
                _block("Evidence available to the receptionist", _sources(test_case)),
            ]
        )


def grounded_facts_graph() -> DeepAcyclicGraph:
    """The graph: did it state anything? → does the evidence match it? → ask, with the evidence."""
    states = StatesAnyFactNode(criteria=STATES_ANY_FACT, label="states a checkable fact")
    states.add_verdict(False, score=PASS)

    matched = EveryFactMatchedNode(criteria=EVERY_FACT_MATCHED, label="every fact matched")
    states.add_verdict(True, then=matched)
    matched.add_verdict(True, score=PASS)

    leftovers = LeftoverEvidenceNode(
        instructions=RENDER_LEFTOVERS,
        output_label="Unmatched claims and the evidence for them",
        label="leftovers",
    )
    matched.add_verdict(False, then=leftovers)

    # The only judge call in this metric, and it never sees a rule with an exception:
    # one question, the claims in front of it, the evidence underneath.
    supported = ConversationalBinaryJudgementNode(criteria=IS_IT_SUPPORTED, label="supported")
    leftovers.add_node(supported)
    supported.add_verdict(True, score=PASS)
    supported.add_verdict(False, score=FAIL)

    return DeepAcyclicGraph([states])


def _leftovers(test_case: ConversationalTestCase) -> list[grounding.Datum]:
    """The stated data the evidence does not account for, recomputed per node (regexes are free)."""
    turns = test_case.turns
    return grounding.unsupported(grounding.stated_data(turns), grounding.evidence_of(turns))


def _turns_of(test_case: ConversationalTestCase, data: list[grounding.Datum]) -> list[str]:
    """The assistant messages the leftover claims were said in, once each."""
    indexes = sorted({datum.turn for datum in data})
    return [f"turno {index}: {test_case.turns[index].content}" for index in indexes]


def _sources(test_case: ConversationalTestCase) -> list[str]:
    """The sources themselves, unflattened, so the judge reads what the agent could read."""
    said = [turn.content for turn in test_case.turns if turn.role == "user"]
    outputs = [
        str(call.output)
        for turn in test_case.turns
        for call in (turn.tools_called or [])
        if call.output is not None
    ]
    return [
        CLINIC,
        "Lo que dijo el paciente: " + " / ".join(said),
        "Lo que devolvieron las herramientas:\n" + "\n".join(outputs),
    ]


def _summary(what: str, data: list[grounding.Datum]) -> str:
    """One line, because a node's reason is one line in the verbose log — the rest is dropped."""
    if not data:
        return f"Nothing {what}."
    return f"Data {what}: " + "; ".join(str(datum) for datum in data)


def _block(title: str, items: list[str]) -> str:
    """A titled block for a task node's output, where a reader has room to read."""
    return f"{title}:\n" + ("\n".join(items) if items else "(none)")
