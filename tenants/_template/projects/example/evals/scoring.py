"""What this project's finished calls are scored on, automatically, once they hang up.

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
"""

from core.scoring.rules import ScoringRules

from .dag import OTHER_BUSINESS_TERMS, TU_FORMS

JUDGE_STEPS = (
    "Read the whole call and say what the person rang this business for.",
    "Decide whether the agent got them there, or told them clearly that it could not and what "
    "to do instead. Both count as done; only leaving them hanging does not.",
    "Penalise a call that ended with the request unresolved and unaddressed, or that went "
    "round the same question repeatedly.",
    "Do not judge tone, register or whether the facts stated were true: other checks own "
    "those, and marking them again here doubles a single fault.",
    "Score 10 when the person got what they rang for or a clear honest no, 5 when it was half "
    "done, 0 when the call left them where it found them.",
)

RULES = ScoringRules(
    forbidden_register=TU_FORMS,
    other_business=OTHER_BUSINESS_TERMS,
    judge_steps=JUDGE_STEPS,
    judge_name="Call quality",
)
