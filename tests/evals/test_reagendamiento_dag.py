"""The hard policy of ms-3, on conversations nobody wrote: nothing is written before a yes.

Eight simulated calls. Five move a cita the patient already has — two
straightforward, two where they change their mind twice, one where they back out
at the confirmation — and three ask for a first one, ms-18's errand, with the
same three shapes minus a wobble. Each is scored by `consent_policy()`, which is
1.0 or 0.0 and nothing in between.

`consent_policy()` and not `never_book_before_yes()`, deliberately. The clinic
has two irreversible doors now, and a metric that watches only `book_slot` ends
at its first computed node on a new-booking call and reports a 1.0 without
reading anything. One graph over both writes is the only version of this suite
whose greens mean something on all eight calls; `tests/test_consent_dag.py`
pins that reasoning deterministically and for free.

One test function for the eight, which is a cost decision and not a style one.
The expensive half is the simulation: eight conversations of real Haiku on both
sides of the line. Parametrised over eight cases, `deepeval test run -n 3` would
hand them to three workers, each of which would build the module fixture and
simulate all eight again — twenty-four conversations to score eight. So the
suite runs them once, scores each one, and reports every score in the failure
message, which is also what the closing note of the card needs to quote.

Run with `deepeval test run tests/evals` (needs ANTHROPIC_API_KEY).
"""

import pytest

from core.testing import deepeval as bridge

pytestmark = pytest.mark.evals

TENANT, PROJECT = "clinica-norte", "reagendamiento"

metrics = bridge.project_metrics(TENANT, PROJECT)
simulator = bridge.project_evals(TENANT, PROJECT, "simulator")


def test_no_simulated_call_ever_writes_before_the_patient_says_yes() -> None:
    scored = {}
    for case in simulator.simulate_calls():
        metric = metrics.consent_policy()  # fresh: a metric holds its last score
        scored[case.name] = (metric.measure(case), _why(metric))

    told = "\n".join(f"{name}: {score} — {why}" for name, (score, why) in scored.items())
    print(told)
    assert len(scored) == len(simulator.goldens())
    assert all(score == 1.0 for score, _ in scored.values()), told


def _why(metric) -> str:
    """The node chain: the metric has no generated summary, because it makes no model call."""
    return " | ".join(bridge.node_chain(metric))
