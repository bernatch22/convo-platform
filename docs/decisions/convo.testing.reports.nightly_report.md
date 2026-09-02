# `convo.testing.reports.nightly_report`

The reasoning that used to live in the docstrings of `convo/testing/reports/nightly_report.py`; the code keeps one line per symbol.

## module

Three artifacts, and each one exists because the other two cannot do its job.

  the PAGE   `tmp/evals/<date>/index.html` — every score next to the transcript
             of the call that earned it. This is what a person opens the
             morning after a red night, and the only artifact that answers
             "what did the agent actually say".
  the INDEX  `tmp/evals/index.tsv` — one line per suite per night, appended
             forever. It answers the question a page cannot: is this metric
             drifting, or did it break today? `column -t -s$'\t'` and read it.
  the ROW    `POST /evals/runs` — the nightly beside every hand-started run on
             the console's evals screen, diffed against the previous one. A
             console that is down never turns a green night red: the page on
             disk is still the evidence and the exit code is still the verdict.

Everything here takes plain dicts — `nightly.Result.view()` — and never the
run's own objects, which is what keeps this module free of the half of the
nightly that spends money.

## worst

Failing before low, because a threshold is a judgement somebody made: a
metric at 0.95 that its project set 0.99 for is a regression, and one at
0.60 that passes at 0.50 is the design working.
