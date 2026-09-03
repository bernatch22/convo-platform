# `convo.scoring.checks`

The reasoning that used to live in the docstrings of `convo/scoring/checks.py`; the code keeps one line per symbol.

## module

No judge, no key, no cost: hand these a list of events and the turns replayed
from them and they decide. They are what makes ring 4 affordable on EVERY call
— a shop doing four hundred calls a day pays nothing for the part of the score
that catches the failures a business actually cares about, and the one judge
call after them is the exception, not the pipeline.

Two of the four are the ring-1 scanners reused verbatim, deliberately:
`convo.testing.metrics.register.slips` and `convo.testing.metrics.leakage.mentions` are the same
whole-word passes over flattened text that score the goldens, so a rule that
fails in CI fails on a real call for the same reason and with the same wording.
A second implementation would have drifted within a milestone.

The other two read the log's own vocabulary rather than the transcript:

- **consent** is `tool.call` with `side_effect: irreversible` and no
  `confirm.granted` for that tool before it. The executor records the side
  effect on every tool event and `ConfirmTask` records the grant, so the whole
  policy is a walk over two kinds. A call the guard REFUSED never becomes a
  `tool.call` at all — `tool.refused` is written instead — which is why a
  correctly defended call scores a pass here: nothing irreversible happened.
- **no_errors** is the provider path: an `error` event, or an outcome of
  `error`. Not the agent's fault, and still the difference between a call that
  worked and one that did not.

Open source note: nothing below knows a clinic from a shop. The two word lists
arrive as `ScoringRules`; the other two checks need no project data at all.

## consent

Vacuously true when nothing irreversible ran, which is the same answer the
ring-1 consent graph gives and for the same reason: a call that booked
nothing cannot have booked without permission.
