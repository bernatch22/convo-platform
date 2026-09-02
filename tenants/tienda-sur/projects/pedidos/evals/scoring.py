"""What Tienda Sur's finished calls are scored on, automatically, once they hang up.

The mirror of the clinic's file, and the point of having two: the platform's
scorer is the same code, the register is the opposite one (this shop tutea, so
the forms it must never use are the usted ones), and the business next door is
the clinic. Nothing in `core/scoring` knows which is which.

The word lists come from `dag.py`, where the ring-1 metrics already keep them,
so a term added for the suite is watched on real calls the same afternoon.
"""

from convo.scoring.rules import ScoringRules

from .dag import CLINIC_TERMS, USTED_FORMS

JUDGE_STEPS = (
    "Read the whole call and say what the customer rang Tienda Sur for: where an order is, "
    "cancelling one, a size, a return, or shop information.",
    "Decide whether the shop got them there — the state of their order, a cancellation they "
    "agreed to, or a straight answer — or said clearly that it could not and what to do "
    "instead. Both are done; only leaving them hanging is not.",
    "Penalise a call that ended with the customer's question unanswered and unacknowledged, "
    "one that asked for the same order number three times, or one that ignored what they said.",
    "Do not judge whether it tuteed, how it sounded, or whether the tracking codes and prices "
    "it quoted are real. Other checks own those and scoring them again here doubles one fault.",
    "Score 10 when the customer got what they rang for or a clear honest no, 5 when it was "
    "half done, 0 when the call left them exactly where it found them.",
)

RULES = ScoringRules(
    forbidden_register=USTED_FORMS,
    other_business=CLINIC_TERMS,
    judge_steps=JUDGE_STEPS,
    judge_name="Order desk call quality",
)
