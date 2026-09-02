"""The register check: does the agent speak the way the business speaks?

A clinic that addresses patients as "usted" must never say "te"; a shop that
tutees must never say "usted". The rule has no degrees — one slip in a call
that has gone the other way for five minutes sounds like a different person
picking up the phone — and a GEval asked about tone scores it 0.8 and moves on.

So it is a graph with a single `DeterministicNode` and no judge at all: each
project declares the forms it must never use (`evals/dag.py`) and this scans
every assistant turn for them, whole words, on flattened text, so "usted" never
trips "te" and "disculpa" never trips "disculpe".

Open source note: the scan is the reusable part and the word lists are not.
A language with no T-V distinction still has registers a business cares about
(a name versus a title, slang versus formal), and the shape is the same.
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
    """One node: does the agent ever slip out of the register the business speaks in?

    A register is a word list, not a judgement — «¿cuál te viene mejor?» in a
    call that has been "usted" throughout is a defect whatever the rest of the
    sentence does, and a judge asked about tone scores it 0.8 and moves on.
    Forms are matched whole, on flattened text, so "usted" never trips "te".
    """
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
