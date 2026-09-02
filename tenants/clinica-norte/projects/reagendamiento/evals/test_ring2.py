"""Ring 2 for this clinic: two people really phone reception, and the hard policies still hold.

Decisions: docs/decisions/tenants.clinica-norte.projects.reagendamiento.evals.test_ring2.md
"""

from pathlib import Path

import pytest
from deepeval import assert_test

from convo.testing.metrics import deepeval as bridge
from convo.testing.reports import ring2_goldens

pytestmark = pytest.mark.evals

TENANT, PROJECT = "clinica-norte", "reagendamiento"

GOLDENS = ring2_goldens.load(Path(__file__).parent / "ring2_goldens.json")
metrics = bridge.project_metrics(TENANT, PROJECT)


@pytest.mark.parametrize("golden", GOLDENS, ids=lambda golden: golden.name)
async def test_a_real_call_keeps_the_clinics_policies(golden) -> None:
    """Phone the clinic as this persona and score what came back, wire and log."""
    run = await ring2_goldens.call(golden, TENANT, PROJECT)

    print(run.summary())
    assert run.out_of_character() is None, f"{golden.name}: {run.out_of_character()}"
    for source, chosen in ring2_goldens.metrics_by_source(golden, metrics).items():
        assert_test(run.case(source), chosen)
