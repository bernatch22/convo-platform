# `convo.scoring.report`

The reasoning that used to live in the docstrings of `convo/scoring/report.py`; the code keeps one line per symbol.

## module

Pure: no deepeval, no store, no model. What is here is the vocabulary — a
`Check`, a `ScoreReport` and the payload they become — plus `finished`,
`already_scored` and `next_seq`, which are the whole of the scorer's bookkeeping
and the part most worth reading on its own.

Two decisions live in this file and nowhere else:

**A check has three answers, not two.** `passed=None` means "this call had
nothing to check" — a project that declares no forbidden register, a call that
ran no irreversible tool at all. It is dropped from the average instead of
counted as a pass, because a vacuous 1.0 is how a suite starts looking healthier
the less it measures.

**A finished call is not the same as a closed one.** `close_session` runs in a
shutdown callback, and a job killed mid-call never gets there: its row keeps a
null outcome forever. So a session is also finished when its log has gone quiet
for `STALE_S` — which is exactly what a dropped call looks like from here.

## Check

`score` is the judge's raw 0-1 and stays None for a check code decided:
consent either happened or it did not, and a 0.6 would be an invention.
