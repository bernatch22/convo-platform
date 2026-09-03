# `tenants.tienda-sur.projects.pedidos.evals.grounding`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/evals/grounding.py`; the code keeps one line per symbol.

## module

The machinery — extract, match, escalate the remainder — is
`convo.testing.metrics.grounding`, shared with the clinic next door. What lives here is
the half that is a shop: an order number, a tracking code, a carrier's name,
and the shop's own information sheet as the first source of every answer.

The four extractors this project adds are the four things a customer would act
on and an agent could invent: a number that is not their order, an incident
number that leads to somebody else's complaint or to nothing, a tracking code
that leads nowhere, and a carrier that never had the parcel. Prices, clock
hours and phone numbers come free from `convo/`.

The incident number is checked against the CALL for the same reason the carrier
is, and one of its own: it does not exist until the helpdesk mints it, so the
only source that can ever ground it is what the tool returned in this very
conversation.

Two functions are the whole contract with the platform: `stated_data(turns)`
and `evidence_of(turns)`.
