# `convo.scoring.judge`

The reasoning that used to live in the docstrings of `convo/scoring/judge.py`; the code keeps one line per symbol.

## module

One metric, one model call, per finished call. Everything else in the score is
code, so this is the whole of the budget and the whole of the exposure — and it
is spent on the one question code genuinely cannot answer: did this call do for
the person what they rang up for?

Three gates stand in front of it, in the order they are cheapest to check:

1. **Under three turns, nothing is judged.** A wrong number, a hang-up on the
   greeting, a "perdón, me he equivocado" — there is no conversation to have an
   opinion about, and a judge handed one invents one. The deterministic checks
   still run; the score is theirs alone.
2. **The transcript is cut to the last `MAX_TURNS`, each turn to `MAX_CHARS`.**
   A forty-minute call and a two-minute call must cost the same to score, and
   the end of a call is where completion is visible.
3. **The worst case is priced before it is bought.** Input estimated from the
   rendered prompt, output assumed at its ceiling, both at the same
   `core.observability.prices` table `session.end` is priced with. Over the cap
   → the judge does not run and the log says so, with both numbers.

The euros written into `session.score` are then the REAL ones, from the token
counts DeepEval reports back, not the estimate: the estimate exists to refuse,
the measurement to audit.

Open source note: `ConversationalGEval` with explicit `evaluation_steps` is the
whole trick to a one-call judge — leave the steps out and DeepEval spends a
second model call generating them, on every session, forever.

## judge

Returns the check to add to the report (None when nothing was judged) and
the `JudgeRun` that goes into the log either way: a skip is an audited
event, not a silence.

## estimated_eur

Priced from the same table `session.end` uses, so the euros in a score and
the euros in a bill are the same currency measured the same way. An unpriced
model estimates as free — and is then reported as it really cost, never
guessed at.

## _trim

A fresh case rather than an edit: the one the caller holds is the log's own
reading of the call and other metrics read it afterwards.
