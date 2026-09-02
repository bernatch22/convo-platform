# `convo.state.outcomes`

The reasoning that used to live in the docstrings of `convo/state/outcomes.py`; the code keeps one line per symbol.

## module

The session list answers "who called and how did it go". This answers the
other question an operator actually has at the end of a week: *how many
appointments did we book, move and cancel, and can I see the call behind each
one*. Both readings come out of the same place — there is no second table, no
counter incremented beside the write, no nightly rollup. The log IS the table:
`tool.call` with `side_effect: irreversible` is a transaction, `confirm.granted`
before it is the caller's yes, and `tool.result` closes it with the one line
the tool's `result_summary` was allowed to keep.

Three decisions are worth arguing with, so they are written down here.

**Computed on read.** A rollup table would be a second truth to keep honest,
and the first thing to disagree with the log after a migration. Counting is a
walk over events the store already has indexed by session; at box volumes (a
few hundred calls a day) it costs milliseconds, and the window is bounded by
`days` precisely so it stays that way. When a deploy is doing thousands a day
the fix is a materialised view over these same events, not a counter written
by the executor — the log must remain the only place a transaction is
recorded.

**The verb is the tool's own name, never a list.** Nothing in this module
knows that a clinic books slots or a shop cancels orders. A transaction is
`side_effect == "irreversible"`, and the verb is whatever `payload["tool"]`
said. A project that declares a new irreversible tool tomorrow appears on the
board the first time it runs, with no code changed here and none in the UI —
`tests/test_outcomes.py` pins that with a tool name this file has never heard
of.

**The summary is reused, never re-rendered.** `result_summary` ran inside the
job process, next to the adapter that knew which fields were safe, and what it
produced went through the session's PII mask before it was written. Re-rendering
it here would mean reading a result this process does not have and re-deciding
a question a project already answered. So the board shows the stored line
verbatim, or nothing at all — a tool that declared no renderer has no summary
to show, and inventing one would be worse than the dash.

A refused call (`tool.refused`) is deliberately NOT a row: the guard stopped
it, nothing happened to the business, and a board of outcomes that listed
non-events would make a well-defended call look like a busy one. Refusals are
evidence, and they are already scored — `core.scoring.checks.consent` reads
the same two kinds from the same log.

## _of_session

The pairing is the log's own order and nothing else. There is no call id in
an event, so a result closes the OLDEST open call of the same name — the
executor awaits one call at a time, which is what makes that correct; the
same reasoning `core.testing.replay.tools` runs on.

A grant is consumed by the call it authorised, so a caller who said yes
once and a tool that ran twice leaves the second transaction unconfirmed,
visible, and exactly as damning as it should be.
