# `convo.testing.metrics.dag`

The reasoning that used to live in the docstrings of `convo/testing/metrics/dag/__init__.py`; the code keeps one line per symbol.

## module

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
  matches (`convo.testing.metrics.grounding`), and the one judge call only ever sees what
  was left over, with the evidence attached.

`nodes.py` holds what both are built from: the transcript params, the two
scores, and `DeterministicNode` — a node that computes its answer instead of
generating it. All three are re-exported here, so `from convo.testing import dag`
and every `dag.<name>` a project writes keep working unchanged.

What a project still owns: its knowledge block, the words it can be wrong
about, the two tool names, and the wording of the one genuine language question
in each graph. That is `tenants/<id>/projects/<p>/evals/`.
