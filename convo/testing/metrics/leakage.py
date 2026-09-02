"""Cross-tenant leakage: does one business's agent ever answer as the business next door?

One worker serves every tenant, so the only thing keeping Clínica Norte's
doctors out of Tienda Sur's answers is that each session is built from its own
project data. That is an architectural claim, and a claim is worth a metric:
ask the shop for a traumatology appointment, ask the clinic where a parcel is,
and read what comes back.

Two questions, in the order of what they cost:

1. **Did the reply name anything that belongs to the other business?** A word
   scan, not a judge — the other tenant's proper nouns are a list (its brand,
   its site, its doctors, its carriers, its phone), and a reply containing one
   of them is a 0.0 whatever the sentence around it was doing. This is the node
   that can actually catch a leak, and it costs nothing.
2. **Did it stay in its own business and redirect politely?** The genuine
   language question, and the only judge call: an agent that invents a booking
   system it does not have leaks nothing by name and is still wrong.

The scan is `core.testing.register.slips`, the same whole-word pass over
flattened text the register check uses, so «norte» never trips on «Clínica
Norte» and an accent or a full stop in a doctor's name never hides a leak.

Open source note: the graph is reusable as it stands and the word lists are
not. Any platform running several businesses on one runtime can copy this file;
what each tenant has to write is the short list of nouns that only ever belong
to somebody else.
"""

from deepeval.metrics import DeepAcyclicGraph
from deepeval.metrics.conversational_dag import ConversationalBinaryJudgementNode
from deepeval.metrics.dag.schema import BinaryJudgementVerdict

from convo.testing.metrics import grounding, register
from convo.testing.metrics.dag import FAIL, PASS, TRANSCRIPT, DeterministicNode

NAMES_THE_OTHER_BUSINESS = "Computed: does any agent turn name something of the other business?"


def mentions(turns: list, terms: tuple[str, ...]) -> list[tuple[int, str]]:
    """Every (turn, term) where the agent named something that belongs to another business.

    Terms are flattened before the scan, so a project writes its neighbour's
    nouns the way they are spelled — «Clínica Norte», «Dr. Alberto Navarro» —
    and still matches what a model actually says.
    """
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
    """Named the other business? → 0.0. Otherwise: did it stay in its own and redirect well?

    `other_terms` is the neighbour's proper nouns; `criteria` is the one
    sentence this project wants a judge to answer about a question it cannot
    serve. Both are project data (`tenants/<id>/projects/<p>/evals/dag.py`) —
    the graph knows nothing about either business.
    """
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
