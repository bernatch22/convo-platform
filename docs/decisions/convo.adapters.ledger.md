# `convo.adapters.ledger`

The reasoning that used to live in the docstrings of `convo/adapters/ledger.py`; the code keeps one line per symbol.

## module

A demo adapter is built fresh per session and keeps its book in memory, which
is right for a conversation and useless for a console: the control plane is a
different process, so an appointment booked in a call would never be visible
to anyone who was not on that call. A real deployment has no such problem —
the agenda is a system both processes reach over HTTP — so the fake needs the
one property the real thing already has: the rows outlive the process that
wrote them, and a second process can read them.

That is all this is. It is not a second event log and it is not a cache of one:
the append-only log records what the PLATFORM did (`core/outcomes.py` counts
transactions off it, and its summaries are PII-filtered by design). This file
records what the BUSINESS SYSTEM now holds — the reservation itself, with the
name on it — because a booking system is exactly the place a customer's own
data is allowed to live, and an operator console is exactly who it is for.

Two decisions worth arguing with.

**Write-through, never read back into a conversation.** An adapter records a
row here after it writes it, and nothing in a session ever reads it: the
in-memory book stays the seeded demo book, so a call behaves identically to
the way it did before this file existed and no test can be contaminated by
what another one wrote. The console reads the ledger, merged over the seed —
which is the business system's current table, and the only reader that needs
it.

**Last write wins, no locking.** Read the file, replace one row, write it back
through `os.replace` so a reader never sees a half-written file. Two calls
finishing in the same millisecond could lose one row; a demo box does a few
transactions an hour, and the fix for real volume is not a lock file, it is
the real system this file is standing in for.

The path is `CONVO_LEDGER`, defaulting beside the SQLite control plane in
`tmp/`. Tests point it at their own tmp directory (`tests/conftest.py`), which
is why the unit ring never touches the box's book.

## Ledger.record

The key is the business system's own identifier; an empty one is a bug
upstream and is dropped rather than filed under the empty string.
