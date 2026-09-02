# `tenants._template.projects.example.evals.scoring`

The reasoning that used to live in the docstrings of `tenants/_template/projects/example/evals/scoring.py`; the code keeps one line per symbol.

## module

Ring 4 scores every call the platform completes, without anybody asking: four
checks decided by code (consent, register, cross-tenant leakage, provider
errors) and at most one judged metric, under a hard cap. This file is the only
thing a new project has to write for it.

TODO(copy): reuse the two word lists your `dag.py` already declares — never
restate them here, or the suite and the live scorer will drift apart — and
rewrite `JUDGE_STEPS` in terms of what YOUR callers ring up for. Delete
`judge_steps` entirely to take the platform's default
(`core.scoring.judge.DEFAULT_STEPS`), which asks the same question in general
terms.

A project that deletes this file is still scored: the checks that need no
business vocabulary run, and the two that do are reported as "not applicable"
rather than as passed. A project that wants no score at all sets
`scoring=False` on its `Project` instead — that is a decision about the
business, and it belongs next to the voice and the greeting.
