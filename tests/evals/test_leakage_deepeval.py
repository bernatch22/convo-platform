"""One worker, two businesses: ask each one for what only the other does.

The ms-5 claim is that nothing in `core/` knows a clinic from a shop — same
registry, same router, same session code, same process. If that is true, a
clinic asked where a parcel is has no way to answer as the shop next door, and
a shop asked for a traumatology appointment has no doctors to offer. If it is
false, this is where it shows.

Two cases, one per tenant, and each is the golden marked `leakage` in that
project's own `goldens.json` — the same file the rest of the suite reads, so
the call is also scored for tone, register and grounding by
`test_reception_deepeval.py` / `test_pedidos_deepeval.py`. What is added here is
the metric that is about the OTHER business, and it lives in each project
because the words are each project's: its neighbour's proper nouns, and the
sentence a judge is asked about a request it cannot serve.

Cost, deliberately: two conversations and at most two judge calls. The node that
can actually catch a leak is a word scan and costs nothing; the judge is only
paid to say whether an honest refusal was an honest refusal.

Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import json
import pathlib

import pytest
from deepeval import assert_test

from convo.testing import fake_context, run_conversation
from convo.testing.metrics import deepeval as bridge

pytestmark = pytest.mark.evals

TENANTS = [("clinica-norte", "reagendamiento"), ("tienda-sur", "pedidos")]


def leakage_golden(tenant: str, project: str) -> dict:
    """The one golden of a project that asks it for the business next door's work."""
    path = pathlib.Path("tenants") / tenant / "projects" / project / "evals" / "goldens.json"
    goldens = [g for g in json.loads(path.read_text()) if g.get("leakage")]
    if len(goldens) != 1:
        raise AssertionError(f"{tenant}/{project} has {len(goldens)} leakage goldens, expected 1")
    return goldens[0]


@pytest.mark.parametrize(("tenant", "project"), TENANTS, ids=[tenant for tenant, _ in TENANTS])
async def test_a_tenant_never_answers_as_the_business_next_door(tenant: str, project: str) -> None:
    golden = leakage_golden(tenant, project)
    tc = fake_context(tenant, project)

    conversation = await run_conversation(tc, bridge.inputs_for(golden))

    whole_call = bridge.conversational_test_case_for(
        conversation,
        bridge.tool_descriptions(tc),
        scenario=golden["expected_behaviour"],
        name=f"{tenant}: {golden['input']}",
    )
    assert_test(whole_call, [bridge.project_metrics(tenant, project).no_leakage()])
