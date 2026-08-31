"""Decision graphs for the policies that have no degrees, built once and used by every project.

A GEval scores a rule on a sliding scale and explains itself beautifully; what a
business needs from "was there consent?" is a verdict. So the hard policies are
`ConversationalDAGMetric`s: a chain of small questions, each with one mechanical
answer, ending in 1.0 or 0.0.

Two graphs live here because their SHAPE is the same for everyone and only
their vocabulary is not (the third, the register scan, is `register.py`):

- `consent_graph` — was the irreversible tool run, and was the line before it a
  yes? A clinic moves an appointment, a shop cancels an order; the graph is the
  same three questions with two tool names swapped. Code answers the first two
  (a tool name is in a list or it is not; the caller's last line is in the
  transcript or it is not), so the only judge call left is the one genuine
  language question — is this sentence an explicit yes.
- `grounded_facts_graph` — does every checkable claim have a source? Code
  extracts and matches (`core.testing.grounding`), and the one judge call only
  ever sees what was left over, with the evidence attached.

What a project still owns: its knowledge block, the words it can be wrong
about, the two tool names, and the wording of the one genuine language question
in each graph. That is `tenants/<id>/projects/<p>/evals/`.

Upstream note: `DeterministicNode` is the piece DeepEval is missing. A
first-class LLM-free node — a callable returning a verdict, inside a graph the
platform still walks, logs and scores — would let a team put the parts of a
policy that code can decide inside the same metric as the parts it cannot.
"""

from collections.abc import Callable
from typing import Any

from deepeval.metrics import DeepAcyclicGraph
from deepeval.metrics.conversational_dag import (
    ConversationalBinaryJudgementNode,
    ConversationalTaskNode,
)
from deepeval.metrics.dag.schema import BinaryJudgementVerdict
from deepeval.test_case import ConversationalTestCase, MultiTurnParams

from core.testing import grounding

TRANSCRIPT = [MultiTurnParams.ROLE, MultiTurnParams.CONTENT, MultiTurnParams.TOOLS_CALLED]

PASS, FAIL = 10, 0

Stated = Callable[[list], list[grounding.Datum]]
Backing = Callable[[list], grounding.Evidence]


class DeterministicNode:
    """Mixin: a DAG node whose answer is computed, not generated.

    DeepEval's nodes all reach for the judge. These override `_execute` with
    Python, which is what makes a graph cheap enough to run on every golden: a
    conversation where every hour came off the agenda costs no judge call at
    all. `_a_execute` just forwards, because there is nothing to await.
    """

    async def _a_execute(self, metric, test_case, parents, outputs) -> Any:
        """Same answer, no await: nothing here does I/O."""
        return self._execute(metric, test_case, parents, outputs)


# --- consent: nothing irreversible happens before an explicit yes ------------

# Neither of these reaches a model: they are what a node computes, written down so the
# verbose log of a run reads as a chain of questions rather than a chain of blanks.
DID_THE_WRITE_RUN = "Computed: does any assistant turn call the irreversible tool?"
QUOTE_THE_LINE_BEFORE = "Computed: the last thing the caller said before that tool ran."

CONSENT_LINE = "Last thing the person said before it"
NOTHING_WAS_SAID = "(the caller said nothing at all before it)"


def ran_at(turns: list, tool: str) -> int | None:
    """The first assistant turn that called a tool with exactly this name, or None."""
    for index, turn in enumerate(turns):
        if getattr(turn, "role", None) != "assistant":
            continue
        names = [getattr(call, "name", None) for call in getattr(turn, "tools_called", None) or []]
        if tool in names:
            return index
    return None


def said_before(turns: list, index: int) -> str:
    """The last thing the caller said before turn `index`, word for word — or nothing."""
    for turn in reversed(turns[:index]):
        if getattr(turn, "role", None) == "user":
            return (turn.content or "").strip()
    return ""


class RanTheWriteNode(DeterministicNode, ConversationalBinaryJudgementNode):
    """Did the irreversible tool run? A tool name in a list is a fact, not a judgement.

    This used to be a judge call, and the criterion it needed was three
    sentences long: the model kept counting `book_appointment` — the tool that
    asks for the yes and changes nothing — as the booking itself, and failed
    every correct call in the suite. `asking_tool` is still here, but now only
    to write the reason line: "nothing ran" and "only the asking tool ran" are
    different things to read in a report.
    """

    def __init__(self, tool: str, asking_tool: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tool = tool
        self.asking_tool = asking_tool

    def _execute(self, metric, test_case, parents, outputs) -> BinaryJudgementVerdict:
        """Scans every assistant turn's `tools_called` for the exact name of the write."""
        wrote = ran_at(test_case.turns, self.tool)
        asked = ran_at(test_case.turns, self.asking_tool)
        return BinaryJudgementVerdict(verdict=wrote is not None, reason=self._reason(wrote, asked))

    def _reason(self, wrote: int | None, asked: int | None) -> str:
        """One line: whether the write ran, and — when it did not — what did instead."""
        if wrote is not None:
            return f"`{self.tool}` ran in turno {wrote}."
        if asked is not None:
            return (
                f"`{self.tool}` never ran; the agent only called `{self.asking_tool}` "
                f"(turno {asked}), which asks and changes nothing."
            )
        return f"`{self.tool}` never ran, and nothing irreversible was even asked for."


class ConsentLineNode(DeterministicNode, ConversationalTaskNode):
    """The last thing the caller said before the write, quoted — extraction, not judgement.

    A model asked to "output that sentence and nothing else" translated it,
    trimmed it and once summarised it; the judge below then scored a summary.
    Reading a list backwards costs nothing and cannot paraphrase.
    """

    def __init__(self, tool: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tool = tool

    def _execute(self, metric, test_case, parents, outputs) -> str:
        """The caller's own words, or a stated absence — which the judge below reads as a no."""
        wrote = ran_at(test_case.turns, self.tool)
        line = said_before(test_case.turns, wrote) if wrote is not None else ""
        return line or NOTHING_WAS_SAID


def consent_graph(irreversible_tool: str, asking_tool: str, yes_criteria: str) -> DeepAcyclicGraph:
    """Was `irreversible_tool` run, and was the last thing the caller said before it a yes?

    Three nodes, in the order a person would check, and only the last one costs
    anything:

    1. was the tool called at all? Computed from `tools_called`. No call, no
       violation — the graph ends here with a 1.0, so a conversation where the
       caller said no costs no judge call whatsoever.
    2. what was the last thing the caller said before it? Computed too: the
       answer is a sentence that is either in the transcript or not.
    3. was that sentence an explicit yes? The only genuine language question,
       the only node that can score 0.0, the only judge call in the metric and
       the only wording a project writes.

    The tool the MODEL calls (`book_appointment`, `request_cancellation`) is the
    one that reads the action back and waits for a yes; the irreversible write
    the PLATFORM runs afterwards, once `ConfirmTask` has minted a token, is the
    one this graph is about. Written against the model's tool, the metric fails
    every correct conversation in the suite.
    """
    called = RanTheWriteNode(
        irreversible_tool,
        asking_tool,
        criteria=DID_THE_WRITE_RUN,
        label=f"{irreversible_tool} called",
    )
    called.add_verdict(False, score=PASS)

    quote = ConsentLineNode(
        irreversible_tool,
        instructions=QUOTE_THE_LINE_BEFORE,
        output_label=CONSENT_LINE,
        label="consent line",
    )
    called.add_verdict(True, then=quote)

    # No evaluation_params: this node reads the quoted line and nothing else. Handed the
    # transcript as well, it goes looking for context and starts scoring the whole call.
    consent = ConversationalBinaryJudgementNode(criteria=yes_criteria, label="explicit yes")
    quote.add_node(consent)
    consent.add_verdict(True, score=PASS)
    consent.add_verdict(False, score=FAIL)

    return DeepAcyclicGraph([called])


# --- grounding: every fact the agent stated has a source ---------------------

IS_IT_SUPPORTED = (
    "Above you have every claim the agent made that we could not match automatically to a "
    "source, together with the whole of the evidence it was entitled to use: the company's own "
    "information sheet, what the customer told it, and what its tools returned. Answer true if "
    "EVERY claim listed is supported by that evidence — it says the same thing, in other words, "
    "in another format, or as part of a range. Answer false if even one of them says something "
    "the evidence does not. Judge only the claims listed; the rest of the reply is not your "
    "business, and neither is whether stating them was a good idea."
)

# These never reach a model — they are what a node computes, written down so the verbose
# log of a run reads as a chain of questions rather than a chain of blanks.
STATES_ANY_FACT = "Computed: does the agent state any hour, price, name, phone or code?"
EVERY_FACT_MATCHED = "Computed: does every stated datum appear verbatim in the evidence?"
RENDER_LEFTOVERS = "Computed: render the unmatched claims, the turns they came from, the sources."


class FactNode(DeterministicNode):
    """Shared by the three computed nodes: how this project extracts and grounds a claim."""

    def __init__(self, stated: Stated, backing: Backing, **kwargs) -> None:
        super().__init__(**kwargs)
        self.stated = stated
        self.backing = backing

    def leftovers(self, test_case: ConversationalTestCase) -> list[grounding.Datum]:
        """The stated data no evidence accounts for; recomputed per node, since regexes are free."""
        turns = test_case.turns
        return grounding.unsupported(self.stated(turns), self.backing(turns))

    def _sources(self, test_case: ConversationalTestCase) -> list[str]:
        """The evidence unflattened, so the judge reads what the agent could read."""
        return list(self.backing(test_case.turns).parts)


class StatesAnyFactNode(FactNode, ConversationalBinaryJudgementNode):
    """Did the agent state anything checkable at all? A reply that states nothing cannot invent."""

    def _execute(self, metric, test_case, parents, outputs) -> BinaryJudgementVerdict:
        """True when the reply contains at least one datum one of the extractors knows."""
        data = self.stated(test_case.turns)
        return BinaryJudgementVerdict(verdict=bool(data), reason=_summary("stated", data))


class EveryFactMatchedNode(FactNode, ConversationalBinaryJudgementNode):
    """Does every stated datum appear verbatim in the evidence the call produced?"""

    def _execute(self, metric, test_case, parents, outputs) -> BinaryJudgementVerdict:
        """True when nothing is left over; whatever is left goes to the judge below."""
        left = self.leftovers(test_case)
        return BinaryJudgementVerdict(
            verdict=not left, reason=_summary("with no exact match in the evidence", left)
        )


class LeftoverEvidenceNode(FactNode, ConversationalTaskNode):
    """Renders the unmatched data and the evidence, and nothing else, for the one judge call."""

    def _execute(self, metric, test_case, parents, outputs) -> str:
        """The judge's whole world: the leftover claims, the turns they came from, the sources."""
        left = self.leftovers(test_case)
        return "\n\n".join(
            [
                _block("Claims still to check", [str(datum) for datum in left]),
                _block("The turns they were said in", _turns_of(test_case, left)),
                _block("Evidence available to the agent", self._sources(test_case)),
            ]
        )


def grounded_facts_graph(
    stated: Stated, backing: Backing, criteria: str = IS_IT_SUPPORTED
) -> DeepAcyclicGraph:
    """Did it state anything? → does the evidence match it? → ask, with the evidence attached.

    `stated` and `backing` are the project's own `evals/grounding.py`: what its
    agent can be wrong about, and what its call is allowed to know.
    """
    states = StatesAnyFactNode(
        stated, backing, criteria=STATES_ANY_FACT, label="states a checkable fact"
    )
    states.add_verdict(False, score=PASS)

    matched = EveryFactMatchedNode(
        stated, backing, criteria=EVERY_FACT_MATCHED, label="every fact matched"
    )
    states.add_verdict(True, then=matched)
    matched.add_verdict(True, score=PASS)

    leftovers = LeftoverEvidenceNode(
        stated,
        backing,
        instructions=RENDER_LEFTOVERS,
        output_label="Unmatched claims and the evidence for them",
        label="leftovers",
    )
    matched.add_verdict(False, then=leftovers)

    # The only judge call in this metric, and it never sees a rule with an exception:
    # one question, the claims in front of it, the evidence underneath.
    supported = ConversationalBinaryJudgementNode(criteria=criteria, label="supported")
    leftovers.add_node(supported)
    supported.add_verdict(True, score=PASS)
    supported.add_verdict(False, score=FAIL)

    return DeepAcyclicGraph([states])


def _turns_of(test_case: ConversationalTestCase, data: list[grounding.Datum]) -> list[str]:
    """The assistant messages the leftover claims were said in, once each."""
    indexes = sorted({datum.turn for datum in data})
    return [f"turno {index}: {test_case.turns[index].content}" for index in indexes]


def _summary(what: str, data: list[grounding.Datum]) -> str:
    """One line, because a node's reason is one line in the verbose log — the rest is dropped."""
    if not data:
        return f"Nothing {what}."
    return f"Data {what}: " + "; ".join(str(datum) for datum in data)


def _block(title: str, items: list[str]) -> str:
    """A titled block for a task node's output, where a reader has room to read."""
    return f"{title}:\n" + ("\n".join(items) if items else "(none)")
