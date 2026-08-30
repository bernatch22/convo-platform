"""The hard policy of ms-3, on conversations nobody wrote: nothing is booked before a yes.

Five simulated calls — two straightforward, two where the patient changes their
mind twice, one where they back out at the confirmation — each scored by the
project's `ConversationalDAGMetric`, which is 1.0 or 0.0 and nothing in between.

One test function for the five, which is a cost decision and not a style one.
The expensive half is the simulation: five conversations of real Haiku on both
sides of the line. Parametrised over five cases, `deepeval test run -n 3` would
hand them to three workers, each of which would build the module fixture and
simulate all five again — fifteen conversations to score five. So the suite
runs them once, scores each one, and reports every score in the failure
message, which is also what the closing note of the card needs to quote.

Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import pytest

from core.testing import deepeval as bridge

pytestmark = pytest.mark.evals

TENANT, PROJECT = "clinica-norte", "reagendamiento"

metrics = bridge.project_metrics(TENANT, PROJECT)
simulator = bridge.project_evals(TENANT, PROJECT, "simulator")


def test_no_simulated_call_ever_books_before_the_patient_says_yes() -> None:
    scored = {}
    for case in simulator.simulate_calls():
        metric = metrics.never_book_before_yes()  # fresh: a metric holds its last score
        scored[case.name] = (metric.measure(case), metric.reason)

    print("\n".join(f"{name}: {score} — {told}" for name, (score, told) in scored.items()))
    assert len(scored) == len(simulator.goldens())
    assert all(score == 1.0 for score, _ in scored.values()), "\n".join(
        f"{name}: {score} — {told}" for name, (score, told) in scored.items()
    )
