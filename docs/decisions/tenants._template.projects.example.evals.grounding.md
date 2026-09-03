# `tenants._template.projects.example.evals.grounding`

The reasoning that used to live in the docstrings of `tenants/_template/projects/example/evals/grounding.py`; the code keeps one line per symbol.

## module

The machinery — extract, match, escalate the remainder — is
`convo.testing.metrics.grounding`, shared by every tenant. What lives here is the
vocabulary: the kinds of claim a customer would ACT on and an agent could
invent. Clock hours, prices and phone numbers come free from `convo/`.

TODO(copy): one extractor per thing of yours that has a canonical form — an
order number, a policy number, a carrier, a professional's name. A claim no
extractor knows is never checked, so this list is the ceiling of the grounding
metric.

Two functions are the whole contract with the platform: `stated_data(turns)`
and `evidence_of(turns)`.
