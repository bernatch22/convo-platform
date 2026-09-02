"""Every fact the agent stated has a source — code first, and one judge call for the remainder.

Three computed nodes and one judging node. Code extracts and matches
(`core.testing.grounding`); the judge only ever sees the claims nothing
accounted for, with the evidence attached underneath. A conversation where
every hour came off the agenda costs no judge call at all.
"""

from collections.abc import Callable

from deepeval.metrics import DeepAcyclicGraph
from deepeval.metrics.conversational_dag import (
    ConversationalBinaryJudgementNode,
    ConversationalTaskNode,
)
from deepeval.metrics.dag.schema import BinaryJudgementVerdict
from deepeval.test_case import ConversationalTestCase

from convo.testing.metrics import grounding
from convo.testing.metrics.dag.nodes import FAIL, PASS, DeterministicNode

Stated = Callable[[list], list[grounding.Datum]]
Backing = Callable[[list], grounding.Evidence]

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
