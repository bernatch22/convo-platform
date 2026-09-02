# `convo.testing.reports.nightly_html`

The reasoning that used to live in the docstrings of `convo/testing/reports/nightly_html.py`; the code keeps one line per symbol.

## module

Split from `nightly` for the reason every report in this repo is split — the
numbers are worth reading in isolation and a template is not. Nothing here
computes anything: it renders the plain dicts `nightly._view` hands it, which
are DeepEval's own JSON and nothing added.

The one design decision worth stating: a failing metric is rendered **above**
the transcript of the call it failed on, in the same block, because the whole
point of ring 2 is that a red score is only actionable when you can read what
was actually said out loud. A score with no transcript sends a person back to
the log; a score with the transcript is a bug report.
