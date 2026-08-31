"""Ring 2 for the shop: two people really phone the order desk, and nothing is cancelled unheard.

The clinic's `test_ring2.py` is this file with two names changed, and that is
the point: one runtime, two businesses, and the eval layer has to look like it
too. What differs is entirely data — the shop tutea, it cancels orders instead
of moving appointments, and its goldens are in its own folder.

    deepeval test run tenants/tienda-sur/projects/pedidos/evals/test_ring2.py

Needs the dev stack up — `docker compose -f infra/compose/dev.yml up`, `uvicorn
api:app --port 8090`, `python worker.py dev` — plus `ANTHROPIC_API_KEY`,
`ELEVENLABS_API_KEY` and `SONIOX_API_KEY`. `CONVO_API` points it at another
control plane; the nightly run uses it to call the box.

Both goldens end in a cancellation, so `consent_policy` here is never the empty
kind that passes because nothing irreversible happened: `cancel_order` is in
the log, and the graph has to find a yes in the line before it.
"""

from pathlib import Path

import pytest
from deepeval import assert_test

from core.testing import deepeval as bridge
from core.testing import ring2_goldens

pytestmark = pytest.mark.evals

TENANT, PROJECT = "tienda-sur", "pedidos"

GOLDENS = ring2_goldens.load(Path(__file__).parent / "ring2_goldens.json")
metrics = bridge.project_metrics(TENANT, PROJECT)


@pytest.mark.parametrize("golden", GOLDENS, ids=lambda golden: golden.name)
async def test_a_real_call_keeps_the_shops_policies(golden) -> None:
    """Phone the order desk as this persona and score what came back, wire and log."""
    run = await ring2_goldens.call(golden, TENANT, PROJECT)

    print(run.summary())
    assert run.out_of_character() is None, f"{golden.name}: {run.out_of_character()}"
    for source, chosen in ring2_goldens.metrics_by_source(golden, metrics).items():
        assert_test(run.case(source), chosen)
