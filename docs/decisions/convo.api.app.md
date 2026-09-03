# `convo.api.app`

The reasoning that used to live in the docstrings of `convo/api/app.py`; the code keeps one line per symbol.

## module

The worker never opens a database or takes a business decision; this process
does. One router per resource under `convo/api/`; every handler opens its own
store.

    convo api   # or: uvicorn convo.api.app:app --port 8090

## lifespan

The seed runs once, at startup, and only writes a number the store does not
already carry (`convo.telephony.lines.seed`): the control plane owns the
number → project table, so a fresh database must not answer "no line" for a
number that has been ringing for weeks.

The sweeper is a task of this process and not a cron entry because it must
stop when the control plane stops: a sweeper still judging calls against a
database whose owner has gone is spending money nobody is watching.
`SCORING_SWEEP=0` starts nothing at all.
