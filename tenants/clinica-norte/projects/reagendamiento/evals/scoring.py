"""What Clínica Norte's finished calls are scored on, automatically, once they hang up.

Ring 4 reads this file for the three things it cannot know on its own: the
register this clinic speaks in, the nouns that only ever belong to the shop next
door, and what a good reception call looks like to the one judge it is allowed
to pay for.

The two word lists are the ring-1 ones, imported rather than restated. A rule
that fails a golden in CI has to fail the same way on a real call at three in
the afternoon, and two copies of `TU_FORMS` would have drifted the first time
somebody added "vale, te lo apunto" to one of them.

The judge steps are the clinic's own, and narrower than the platform default on
purpose: reception's job is an appointment moved or an honest no, and a call
that ends with the patient knowing exactly when they are expected is a good call
even if it took six turns to get the name right.
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
