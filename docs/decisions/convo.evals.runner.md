# `convo.evals.runner`

The reasoning that used to live in the docstrings of `convo/evals/runner.py`; the code keeps one line per symbol.

## module

An eval run is minutes of paid LLM traffic, so this is deliberately the most
conservative thing in the codebase:

- **one at a time.** A second request while a run is alive is refused, never
  queued: a queue silently doubles a bill nobody watched being spent.
- **a hard deadline.** A hung judge is killed at `DEADLINE_S` and the run is
  stored as failed with the reason, so the box can never be left with a
  forgotten pytest holding a provider connection open.
- **nothing runs blind.** Every line the child writes is tee'd to
  `tmp/evals/<run id>.log`, and the console reads its tail while it runs.

The child inherits the box's provider keys from `.env` because a suite cannot
judge anything without them. They travel into the child's environment and
nowhere else: no handler echoes an environment and the only thing written to
disk is the child's own output.

## child_env

`.env` first and the real environment over it: an operator who exported a
key for this process meant that key. Nothing here is ever logged.

## metrics_of

DeepEval already aggregates this for us under `metricsScores`: one row per
metric with every case's score and the pass/fail tally. Reading its own file
is what keeps this screen and `deepeval test run` from ever disagreeing.
