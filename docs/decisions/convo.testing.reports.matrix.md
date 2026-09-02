# `convo.testing.reports.matrix`

The reasoning that used to live in the docstrings of `convo/testing/reports/matrix.py`; the code keeps one line per symbol.

## module

The LLM is a slot, and a platform that says so has to be able to show it. This
module is the "show it": it reads what DeepEval already produced for each model
— one `EvaluationResult` per model, from the SAME `goldens.json` — and turns it
into a metric × model table plus the list of goldens the models disagreed on.

Nothing here scores anything. Every number is a `MetricData` DeepEval wrote,
which is what keeps the matrix honest: a comparison that re-judged the runs with
a second criterion would be measuring the criterion, not the models.

Two numbers per cell, and both are needed. The **pass rate** is what CI gates
on, and on a suite of eleven goldens it moves in steps of nine points, so a
model that is worse everywhere can tie one that is worse nowhere. The **mean
score** is the continuous half — it separates "0.72 on a 0.7 threshold" from
"0.95" — and it is meaningless on its own, because a metric with a 1.0
threshold (the DAGs) only ever scores 1.0 or 0.0.

The divergences are the point of the exercise. A golden that passes on one model
and fails on the other is a finding to write down, never a golden to soften: the
suite is the fixed thing and the model is the variable, and the moment a golden
is edited so a specific model passes it, the matrix stops comparing anything.

Open source note: the reusable part is the shape — read a run per model, join on
(metric, case), report the cells and the disagreements. Nothing here knows what
a clinic is.

## read

`evaluate()` answers with one `TestResult` per test case, each carrying the
`MetricData` of every metric that scored it. A case DeepEval could not name
is keyed by its index, so two runs of the same goldens still line up.

## build

Metrics are sorted by name so the table reads the same on every run: the
order `evaluate()` returns them in follows whichever case finished first.

## divergences

Only pairs a model actually scored count as disagreement: a golden one run
never reached is missing evidence, not a difference between two models.
