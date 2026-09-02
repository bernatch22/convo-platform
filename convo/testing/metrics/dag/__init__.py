"""Decision graphs for the policies that have no degrees, built once and used by every project.

A GEval scores a rule on a sliding scale and explains itself beautifully; what a
business needs from "was there consent?" is a verdict. So the hard policies are
`ConversationalDAGMetric`s: a chain of small questions, each with one mechanical
answer, ending in 1.0 or 0.0.

Two graphs live here because their SHAPE is the same for everyone and only
their vocabulary is not (the third, the register scan, is `register.py`):

- `consent.py` — was the irreversible tool run, and was the line before it a
  yes? A clinic moves an appointment, a shop cancels an order; the graph is the
  same three questions with two tool names swapped.
- `grounded.py` — does every checkable claim have a source? Code extracts and
  matches (`core.testing.grounding`), and the one judge call only ever sees what
  was left over, with the evidence attached.

`nodes.py` holds what both are built from: the transcript params, the two
scores, and `DeterministicNode` — a node that computes its answer instead of
generating it. All three are re-exported here, so `from core.testing import dag`
and every `dag.<name>` a project writes keep working unchanged.

What a project still owns: its knowledge block, the words it can be wrong
about, the two tool names, and the wording of the one genuine language question
in each graph. That is `tenants/<id>/projects/<p>/evals/`.
"""

from convo.testing.metrics.dag.consent import (
    CONSENT_LINE,
    NOTHING_WAS_SAID,
    ConsentLineNode,
    RanTheWriteNode,
    consent_graph,
    names_of,
    ran_at,
    said_before,
)
from convo.testing.metrics.dag.grounded import (
    EVERY_FACT_MATCHED,
    IS_IT_SUPPORTED,
    RENDER_LEFTOVERS,
    STATES_ANY_FACT,
    Backing,
    EveryFactMatchedNode,
    FactNode,
    LeftoverEvidenceNode,
    Stated,
    StatesAnyFactNode,
    grounded_facts_graph,
)
from convo.testing.metrics.dag.nodes import FAIL, PASS, TRANSCRIPT, DeterministicNode

__all__ = [
    "EVERY_FACT_MATCHED",
    "FAIL",
    "IS_IT_SUPPORTED",
    "PASS",
    "RENDER_LEFTOVERS",
    "STATES_ANY_FACT",
    "TRANSCRIPT",
    "Backing",
    "CONSENT_LINE",
    "ConsentLineNode",
    "NOTHING_WAS_SAID",
    "RanTheWriteNode",
    "DeterministicNode",
    "EveryFactMatchedNode",
    "FactNode",
    "LeftoverEvidenceNode",
    "Stated",
    "StatesAnyFactNode",
    "consent_graph",
    "grounded_facts_graph",
    "names_of",
    "ran_at",
    "said_before",
]
