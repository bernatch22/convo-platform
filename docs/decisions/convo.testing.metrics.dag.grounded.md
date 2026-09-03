# `convo.testing.metrics.dag.grounded`

The reasoning that used to live in the docstrings of `convo/testing/metrics/dag/grounded.py`; the code keeps one line per symbol.

## module

Three computed nodes and one judging node. Code extracts and matches
(`convo.testing.metrics.grounding`); the judge only ever sees the claims nothing
accounted for, with the evidence attached underneath. A conversation where
every hour came off the agenda costs no judge call at all.

## grounded_facts_graph

`stated` and `backing` are the project's own `evals/grounding.py`: what its
agent can be wrong about, and what its call is allowed to know.
