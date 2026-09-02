# `convo.testing.metrics.register`

The reasoning that used to live in the docstrings of `convo/testing/metrics/register.py`; the code keeps one line per symbol.

## module

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

## register_graph

A register is a word list, not a judgement — «¿cuál te viene mejor?» in a
call that has been "usted" throughout is a defect whatever the rest of the
sentence does, and a judge asked about tone scores it 0.8 and moves on.
Forms are matched whole, on flattened text, so "usted" never trips "te".
