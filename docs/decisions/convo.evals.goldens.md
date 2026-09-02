# `convo.evals.goldens`

The reasoning that used to live in the docstrings of `convo/evals/goldens.py`; the code keeps one line per symbol.

## module

A suite id is a project's own data (`evals/suites.json`); the cases it runs are
its own data too, and they live in two files next to it:

    goldens.json        one TURN each — the caller's line, the behaviour a
                        reviewer expects back, and the tools that must have run
    ring2_goldens.json  one CALL each — a persona, an objective, the lines the
                        caller says out loud, the hard policies that must
                        survive the call, and how many turns it gets

This module joins the two to the suites by the one name a run carries, so the
console can put "ring1 · 12 goldens" next to the runs of `ring1` and show what
those twelve actually are.

**How a suite is joined to its dataset.** `suites.json` gives a pytest target,
and that file NAMES the dataset it reads. So the target is read as text and
searched for the two filenames — never imported, never executed. A suite whose
target mentions neither (its cases are written in python, like a simulator's
personas) is reported with `dataset: null` and no goldens: the screen says
where they live instead of pretending they are not there.

Ring 2 is the one suite no project declares in `suites.json`: it is discovered
by convention (`evals/test_ring2.py`, the same convention `core.testing.nightly`
walks) and files its runs under the id `ring2`.

Everything here is a file read under `tenants/`, so `core` keeps the rule the
whole runtime keeps: it does not import any tenant module, and a project with a
broken `evals/` answers with an empty suite rather than a stack trace.

## datasets

→ `{"tenant", "project", "suites": [{"suite", "target", "dataset", "kind",
"count", "goldens": [...]}]}` — `kind` is `turn`, `call` or `code`, and
`count` is null only for `code`, where the cases are not on disk.
