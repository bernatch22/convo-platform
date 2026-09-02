"""Ring 2 for this clinic: two people really phone reception, and the hard policies still hold.

One test per golden, one live call per test, and each call is the whole
pipeline — ElevenLabs speaks the patient, Soniox hears her, Haiku answers, and
the answer comes back over WebRTC. What is under test is not the model's
wording (ring 1 does that far more cheaply) but the two things only a
microphone can break: an agent talked over mid-sentence, and a patient who
switches into English inside a sentence.

    deepeval test run tenants/clinica-norte/projects/reagendamiento/evals/test_ring2.py

Needs the dev stack up — `docker compose -f infra/compose/dev.yml up`, `uvicorn
api:app --port 8090`, `python worker.py dev` — plus `ANTHROPIC_API_KEY`,
`ELEVENLABS_API_KEY` and `SONIOX_API_KEY`. `CONVO_API` points it at another
control plane; the nightly run uses it to call the box.

Consent is scored on the event log and register on the wire, which is
`core.testing.ring2_goldens`'s doing and worth knowing while reading a failure:
no track carries a tool call, so what the platform DID is a question only the
log can answer.
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
