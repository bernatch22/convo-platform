# `tenants.clinica-norte.projects.reagendamiento.evals.scoring`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/evals/scoring.py`; the code keeps one line per symbol.

## module

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
