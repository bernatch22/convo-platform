# `tenants.clinica-norte.projects.reagendamiento.evals.grounding`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/evals/grounding.py`; the code keeps one line per symbol.

## module

The machinery — extract, match, escalate the remainder — is
`convo.testing.metrics.grounding`, shared by every tenant. What lives here is the half
that is a clinic: an hour said the way a receptionist says it, a professional's
title, a street, and the clinic's own information sheet as the first source of
every answer.

Two functions are the whole contract with the platform: `stated_data(turns)`
and `evidence_of(turns)`. `evals/dag.py` hands them to the graph builder and
`tests/test_grounding.py` asserts on them directly, which is why every rule
below is a unit test that costs nothing to run.
