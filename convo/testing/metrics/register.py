"""The register check: does the agent speak the way the business speaks?

Decisions: docs/decisions/convo.testing.metrics.register.md
"""

from deepeval.metrics import DeepAcyclicGraph
from deepeval.metrics.conversational_dag import ConversationalBinaryJudgementNode
from deepeval.metrics.dag.schema import BinaryJudgementVerdict

from convo.testing.metrics import grounding
from convo.testing.metrics.dag import FAIL, PASS, DeterministicNode

KEEPS_THE_REGISTER = "Computed: does any agent turn use a word from the forbidden register?"


class RegisterNode(DeterministicNode, ConversationalBinaryJudgementNode):
    """True when no assistant turn used a word the business does not say. No judge, ever."""

    def __init__(self, forbidden: tuple[str, ...], **kwargs) -> None:
        super().__init__(**kwargs)
        self.forbidden = forbidden

    def _execute(self, metric, test_case, parents, outputs) -> BinaryJudgementVerdict:
        """A word-boundary scan of every assistant turn against the forbidden forms."""
        found = slips(test_case.turns, self.forbidden)
        reason = "; ".join(f"turno {turn}: «{word}»" for turn, word in found)
        return BinaryJudgementVerdict(
            verdict=not found,
            reason=f"Register slips: {reason}" if found else "No forbidden form was used.",
        )


def register_graph(forbidden: tuple[str, ...]) -> DeepAcyclicGraph:
    """One node: does the agent ever slip out of the register the business speaks in?"""
    node = RegisterNode(forbidden, criteria=KEEPS_THE_REGISTER, label="keeps the register")
    node.add_verdict(True, score=PASS)
    node.add_verdict(False, score=FAIL)
    return DeepAcyclicGraph([node])


def slips(turns: list, forbidden: tuple[str, ...]) -> list[tuple[int, str]]:
    """Every (turn, word) where the agent used a form of the register it must not use."""
    found = []
    for index, turn in enumerate(turns):
        if getattr(turn, "role", None) != "assistant":
            continue
        words = f" {grounding.flatten(turn.content or '')} "
        found += [(index, word) for word in forbidden if f" {word} " in words]
    return found
