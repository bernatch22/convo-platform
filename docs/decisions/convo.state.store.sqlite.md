# `convo.state.store.sqlite`

The reasoning that used to live in the docstrings of `convo/state/store/sqlite.py`; the code keeps one line per symbol.

## module

Built to survive the one failure that matters for an audit log: the process
dying mid-call. WAL journaling with `synchronous=FULL` makes every `append`
durable when it returns, and two triggers refuse UPDATE and DELETE on
`events`. ``routes`, `project_versions` and
`pipeline_overrides` are the three small tables the router reads before a
session starts, and `eval_runs` is what the console's evals screen reads.
Postgres later is this same interface over a pool in `convo/api/app.py`; the job process
never opens a database of its own in production, but on a laptop the file is
the control plane.
