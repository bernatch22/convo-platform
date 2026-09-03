# `convo.evals.filing`

The reasoning that used to live in the docstrings of `convo/evals/filing.py`; the code keeps one line per symbol.

## module

The box can launch a run itself, but most runs are still started by a person or
by CI (`deepeval test run`, `python -m convo.testing.reports.report`). Those are the runs
worth comparing against, so they file themselves here instead of living only in
somebody's terminal scrollback.

A control plane that is not answering is not an error: the local run still
produced its HTML and its exit code. `file_run` says whether the board heard
it and never raises — an eval must not fail because a console was down.

## metrics_from

Every case is scored by every metric, so the run's number for a metric is
the mean over its cases and its tally is how many of them cleared the
threshold — the same aggregation `deepeval test run` prints at the end.
