# `convo.testing.metrics.grounding.evidence`

The reasoning that used to live in the docstrings of `convo/testing/metrics/grounding/evidence.py`; the code keeps one line per symbol.

## module

The other half of `core.testing.grounding` — the half that reads everything
EXCEPT the agent's own claims. `evidence_of` collects the project's knowledge
block, what the caller said (a customer reading their order number out is the
source for the agent repeating it), and the output of every tool the call ran.
Deliberately NOT the agent's own earlier replies, which would let an invention
launder itself one turn later.

Matching is exact after normalising: lowercase, accent-free, punctuation-free,
and hours compared as `HH:MM` so `8:00` in a knowledge block grounds `08:00` on
the phone. What survives that is not proof of an invention — it is the short
list worth paying a judge to look at, with the evidence attached.
