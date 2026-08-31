"""The pieces every decision graph in this codebase is built from: scores, params, a mixin.

Three lines of vocabulary and one idea. The idea is `DeterministicNode`: a DAG
node whose answer is computed instead of generated, which is what makes a graph
cheap enough to run on every golden.

Upstream note: `DeterministicNode` is the piece DeepEval is missing. A
first-class LLM-free node — a callable returning a verdict, inside a graph the
platform still walks, logs and scores — would let a team put the parts of a
policy that code can decide inside the same metric as the parts it cannot.
"""

from typing import Any

from deepeval.test_case import MultiTurnParams

# What a judging node is shown of each turn. Roles and content alone hide the tool calls,
# and a consent graph asked "was it booked?" cannot answer from prose.
TRANSCRIPT = [MultiTurnParams.ROLE, MultiTurnParams.CONTENT, MultiTurnParams.TOOLS_CALLED]

PASS, FAIL = 10, 0


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
