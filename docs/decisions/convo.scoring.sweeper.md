# `convo.scoring.sweeper`

The reasoning that used to live in the docstrings of `convo/scoring/sweeper.py`; the code keeps one line per symbol.

## module

This is the answer to "who runs the scorer", and the answer is deliberately not
the job process. A poll beats a callback here for one reason worth stating: a
job killed by the box — SIGKILL, an OOM, a redeploy mid-call — never gets to
tell anybody it is gone, and those are precisely the calls whose score somebody
wants to see. A sweeper over the log needs nothing from the dying process; it
reads what the log already contains and notices the silence.

Three limits keep it boring:

- `BATCH` sessions per tick, so a box that comes back after an outage with
  three hundred unscored calls spends its judge budget over minutes and can be
  switched off halfway.
- `WINDOW_S` back from now, so it never re-walks a year of history looking for
  work that is not there.
- Idempotency lives in the store, not here (`runner.score_session`): two
  control planes on one database is a supported shape, not a race.

`SCORING_SWEEP=0` turns it off entirely — a deploy that wants scoring only from
the CLI, or a test that wants no background work at all.

## tick

The store is opened HERE, inside the worker thread that will read it: a
SQLite connection belongs to the thread that created it, and this is the
one place in the control plane where the reader is not a request handler.

## due

Oldest first so a backlog drains in the order the calls happened, which is
the order somebody reading the console down the page expects them in.
