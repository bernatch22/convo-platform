# `convo.evals.runs`

The reasoning that used to live in the docstrings of `convo/evals/runs.py`; the code keeps one line per symbol.

## module

A score alone says nothing — 0.82 is good or bad depending on what the same
suite scored yesterday. So every run this module hands out carries, per metric,
the delta against the previous run of the SAME tenant, project and suite. That
is the whole reason the runs are stored at all: a number you can compare.

Plain dicts in, plain dicts out, a `Store` and nothing else — the same shape
`core.control_plane` keeps, so an HTTP handler, a test and a CLI read
identically.

## previous

"Before" is by `started_at`, not by list position: a run filed by CI lands
out of order and would otherwise diff against a future.
