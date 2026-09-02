"""What this project's finished calls are scored on, automatically, once they hang up.

Decisions: docs/decisions/tenants._template.projects.example.evals.scoring.md
"""

from convo.scoring.rules import ScoringRules

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
