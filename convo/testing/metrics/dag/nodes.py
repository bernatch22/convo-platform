"""The pieces every decision graph in this codebase is built from: scores, params, a mixin.

Decisions: docs/decisions/convo.testing.metrics.dag.nodes.md
"""

from typing import Any

from deepeval.test_case import MultiTurnParams

# What a judging node is shown of each turn. Roles and content alone hide the tool calls,
# and a consent graph asked "was it booked?" cannot answer from prose.
TRANSCRIPT = [MultiTurnParams.ROLE, MultiTurnParams.CONTENT, MultiTurnParams.TOOLS_CALLED]

PASS, FAIL = 10, 0


class DeterministicNode:
    """Mixin: a DAG node whose answer is computed, not generated."""

    async def _a_execute(self, metric, test_case, parents, outputs) -> Any:
        """Same answer, no await: nothing here does I/O."""
        return self._execute(metric, test_case, parents, outputs)
