# `convo.scoring.runner`

The reasoning that used to live in the docstrings of `convo/scoring/runner.py`; the code keeps one line per symbol.

## module

The whole of ring 4 in one function, and every refusal it can make is a
sentence a caller can print:

    not found · still running · already scored · scoring is off for this project

None of them is an error. A session scored twice would be the error, and the
store is what prevents it: `session.score` takes the next `seq`, and `events`
has `(session_id, seq)` as its primary key with append-only triggers over it,
so two scorers racing the same call end with one row and one loser — no lock,
no flag column, no window.

Why the imports are inside the function: `core.testing.replay` and the judge
pull `deepeval` in, which costs a second and opens a telemetry client. `api.py`
imports this module at startup and must pay neither until a call is actually
scored.

## score_session

→ `{"session": id, "scored": bool, "score": <payload>|None, "skipped": str|None}`

`store` is opened here when the caller gives none, because this runs in a
worker thread and a SQLite connection belongs to the thread that made it.
`judge=False` runs the free half alone — what a test, or a deploy with no
key, gets for nothing.

## build_report

Split out of `score_session` because it touches neither the store nor the
clock: hand it a list of events and it hands back a verdict, which is how
the checks are tested without a database and without a euro.

## _disabled

A tenant the registry cannot import is unroutable, not opted out, and the
two are reported differently: one is a decision somebody made, the other is
a deploy that is broken and should read as broken.
