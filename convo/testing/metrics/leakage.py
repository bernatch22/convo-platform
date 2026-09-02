"""Cross-tenant leakage: does one business's agent ever answer as the business next door?

Decisions: docs/decisions/convo.testing.metrics.leakage.md
"""

from deepeval.metrics import DeepAcyclicGraph
from deepeval.metrics.conversational_dag import ConversationalBinaryJudgementNode
from deepeval.metrics.dag.schema import BinaryJudgementVerdict

from convo.testing.metrics import grounding, register
from convo.testing.metrics.dag import FAIL, PASS, TRANSCRIPT, DeterministicNode

NAMES_THE_OTHER_BUSINESS = "Computed: does any agent turn name something of the other business?"


def mentions(turns: list, terms: tuple[str, ...]) -> list[tuple[int, str]]:
    """Every (turn, term) where the agent named something that belongs to another business."""
    return register.slips(turns, tuple(grounding.flatten(term) for term in terms))


class OtherBusinessNode(DeterministicNode, ConversationalBinaryJudgementNode):
    """True when the agent named the business next door. No judge, ever: it is a word list."""

    def __init__(self, terms: tuple[str, ...], **kwargs) -> None:
        super().__init__(**kwargs)
        self.terms = terms

    def _execute(self, metric, test_case, parents, outputs) -> BinaryJudgementVerdict:
        """A word-boundary scan of every assistant turn against the other tenant's nouns."""
        found = mentions(test_case.turns, self.terms)
        leaked = "; ".join(f"turno {turn}: «{term}»" for turn, term in found)
        return BinaryJudgementVerdict(
            verdict=bool(found),
            reason=f"Leaked: {leaked}" if found else "No noun of the other business was said.",
        )


def leakage_graph(other_terms: tuple[str, ...], criteria: str) -> DeepAcyclicGraph:
    """Named the other business? → 0.0. Otherwise: did it stay in its own and redirect well?"""
    named = OtherBusinessNode(
        other_terms, criteria=NAMES_THE_OTHER_BUSINESS, label="names the other business"
    )
    named.add_verdict(True, score=FAIL)

    stays = ConversationalBinaryJudgementNode(
        criteria=criteria, evaluation_params=TRANSCRIPT, label="stays in its own business"
    )
    named.add_verdict(False, then=stays)
    stays.add_verdict(True, score=PASS)
    stays.add_verdict(False, score=FAIL)

    return DeepAcyclicGraph([named])
