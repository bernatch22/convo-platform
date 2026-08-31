"""Nothing irreversible happens before an explicit yes — and two of its three answers are code.

A clinic moves an appointment, a shop cancels an order; the graph is the same
three questions with two tool names swapped. Code answers the first two (a tool
name is in a list or it is not; the caller's last line is in the transcript or
it is not), so the only judge call left is the one genuine language question —
is this sentence an explicit yes. What a project still owns is the two names
and the wording of that one question.
"""

from deepeval.metrics import DeepAcyclicGraph
from deepeval.metrics.conversational_dag import (
    ConversationalBinaryJudgementNode,
    ConversationalTaskNode,
)
from deepeval.metrics.dag.schema import BinaryJudgementVerdict

from core.testing.dag.nodes import FAIL, PASS, DeterministicNode

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
