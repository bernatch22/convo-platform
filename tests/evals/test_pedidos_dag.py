"""The hard policy of the shop, on conversations nobody wrote: nothing is cancelled before a yes.

Three simulated calls — one customer who cancels and confirms, one who backs
out as the amount is read to her, one who insists on cancelling an order that
already shipped — each scored by the project's `ConversationalDAGMetric`, which
is 1.0 or 0.0 and nothing in between. The register is scored on the same three
transcripts for free, because a simulated call is where an unscripted "usted"
would appear if the prompt were going to produce one.

One test function for the three, which is a cost decision and not a style one.
The expensive half is the simulation: three conversations of real Haiku on both
sides of the line. Parametrised, `deepeval test run -n 3` would hand them to
three workers, each of which would simulate all three again — nine
conversations to score three. So the suite runs them once, scores each one, and
reports every score in the failure message, which is also what the closing note
of the card needs to quote.

Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import pytest

from core.testing import deepeval as bridge

pytestmark = pytest.mark.evals

TENANT, PROJECT = "tienda-sur", "pedidos"

metrics = bridge.project_metrics(TENANT, PROJECT)
simulator = bridge.project_evals(TENANT, PROJECT, "simulator")


def test_no_simulated_call_ever_cancels_before_the_customer_says_yes() -> None:
    scored = {}
    for case in simulator.simulate_calls():
        consent = metrics.never_cancel_before_yes()  # fresh: a metric holds its last score
        register = metrics.keeps_the_register()
        scored[case.name] = (consent.measure(case), register.measure(case), consent.reason)

    told = "\n".join(
        f"{name}: consent {c}, register {r} — {why}" for name, (c, r, why) in scored.items()
    )
    print(told)
    assert len(scored) == len(simulator.goldens())
    assert all(consent == 1.0 for consent, _, _ in scored.values()), told
    assert all(register == 1.0 for _, register, _ in scored.values()), told
