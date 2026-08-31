"""Ring 4: every call scores itself once it is over, out of the job process.

Rings 1-3 are things a person runs: a suite against goldens, a synthetic caller,
`convo sessions eval <id>` on a call somebody remembered. Ring 4 is the one
nobody runs — the control plane scores every session that ends, writes the
verdict into the same append-only log the call wrote, and the console shows it
as a chip next to the price.

Three rules shape everything in this package:

1. **Nothing happens in the job process.** The job dies with the call; the
   scorer lives in `api.py` and reads the log back from the store. Not one line
   of this runs while somebody is on the phone.
2. **Deterministic first, judge last.** Consent, register, cross-tenant leakage
   and provider errors are decided by code over the log — free, instant, and
   they run on every call. Exactly one LLM call may follow, under a cap proved
   BEFORE it is spent.
3. **The score is a log line.** `session.score` takes the next `seq` and is
   written once; the `(session_id, seq)` primary key is the idempotency guard,
   so a second scorer that raced the first loses and nothing is edited.

Import cost is deliberate: this package's top level touches no `deepeval`, so
`api.py` starts in the same time it always did. `runner.score_session` pulls the
judge stack in on the first call it makes.
"""
