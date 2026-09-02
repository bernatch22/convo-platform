# `convo.testing.metrics.dag.nodes`

The reasoning that used to live in the docstrings of `convo/testing/metrics/dag/nodes.py`; the code keeps one line per symbol.

## module

Three lines of vocabulary and one idea. The idea is `DeterministicNode`: a DAG
node whose answer is computed instead of generated, which is what makes a graph
cheap enough to run on every golden.

Upstream note: `DeterministicNode` is the piece DeepEval is missing. A
first-class LLM-free node — a callable returning a verdict, inside a graph the
platform still walks, logs and scores — would let a team put the parts of a
policy that code can decide inside the same metric as the parts it cannot.

## DeterministicNode

DeepEval's nodes all reach for the judge. These override `_execute` with
Python, which is what makes a graph cheap enough to run on every golden: a
conversation where every hour came off the agenda costs no judge call at
all. `_a_execute` just forwards, because there is nothing to await.
