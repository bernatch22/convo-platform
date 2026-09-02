"""What Clínica Norte's finished calls are scored on, automatically, once they hang up.

Decisions: docs/decisions/tenants.clinica-norte.projects.reagendamiento.evals.scoring.md
"""

from convo.scoring.rules import ScoringRules

from .dag import SHOP_TERMS, TU_FORMS

JUDGE_STEPS = (
    "Read the whole call and say what the patient rang Clínica Norte for: moving an "
    "appointment, cancelling one, or asking something about the clinic.",
    "Decide whether reception got them there — a new hour they agreed to, a cancellation "
    "confirmed, or a plain answer — or told them clearly it could not and what to do instead. "
    "Both are done; only leaving them hanging is not.",
    "Penalise a call that ended with the patient's request unresolved and unaddressed, one "
    "that went round the same question three times, or one that ignored what they asked.",
    "Do not judge whether it said 'usted', how it sounded, or whether the hours it quoted are "
    "real. Three other checks own those and scoring them again here doubles one fault.",
    "Score 10 when the patient got what they rang for or a clear honest no, 5 when it was "
    "half done, 0 when the call left them exactly where it found them.",
)

RULES = ScoringRules(
    forbidden_register=TU_FORMS,
    other_business=SHOP_TERMS,
    judge_steps=JUDGE_STEPS,
    judge_name="Reception call quality",
)
