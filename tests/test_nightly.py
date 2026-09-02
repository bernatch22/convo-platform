"""The nightly's arithmetic: what it would spend, what it refuses to, and what it writes down.

Everything here is the half of the nightly that costs nothing — discovery, the
budget, the reading of DeepEval's own JSON, the page. The half that spends money
is one `subprocess.Popen` and it is not simulated: what is worth testing is that
the run can never reach it with a bill nobody agreed to.
"""

import json

import pytest

from convo.testing.reports import nightly
from convo.testing.reports import nightly_report as report
from convo.testing.reports.nightly import Result, Suite
from convo.testing.reports.nightly_html import page

pytestmark = pytest.mark.unit


def test_it_finds_every_ring_two_suite_the_fleet_declares() -> None:
    """A project has a ring 2 when it has the file — no registry to keep in step."""
    found = nightly.discover()

    assert {suite.id for suite in found} == {
        "clinica-norte/reagendamiento",
        "tienda-sur/pedidos",
    }
    assert all(suite.calls > 0 for suite in found)
    assert all(suite.target.name == "test_ring2.py" for suite in found)


def test_the_number_of_calls_is_the_number_of_goldens() -> None:
    """Each golden is one live call, so the goldens file is the price list."""
    suite = next(s for s in nightly.discover() if s.id == "tienda-sur/pedidos")
    goldens = json.loads(
        (nightly.REPO_ROOT / suite.target).parent.joinpath("ring2_goldens.json").read_text()
    )

    assert suite.calls == len(goldens)


def test_only_narrows_the_sweep_to_one_project() -> None:
    """`--only` is how the forced-regression drill spends one suite instead of the fleet."""
    found = nightly.discover(only=["tienda-sur/pedidos"])

    assert [suite.id for suite in found] == ["tienda-sur/pedidos"]


def test_a_suite_that_does_not_fit_the_budget_is_skipped_whole() -> None:
    """Half a suite scores half a policy, so a suite is taken entire or not at all."""
    suites = [_suite("a", calls=5), _suite("b", calls=5)]

    taken, skipped = nightly.affordable(suites, budget=8)

    assert [s.tenant for s in taken] == ["a"]
    assert [s.tenant for s in skipped] == ["b"]


def test_a_cheap_suite_behind_an_expensive_one_still_runs() -> None:
    """The budget is asked of every suite, not abandoned at the first refusal."""
    suites = [_suite("big", calls=7), _suite("small", calls=1)]

    taken, skipped = nightly.affordable(suites, budget=8)

    assert [s.tenant for s in taken] == ["big", "small"]
    assert skipped == []


def test_the_default_budget_covers_todays_fleet() -> None:
    """The cap has to be a real cap and not a wall: tonight's fleet must fit under it."""
    taken, skipped = nightly.affordable(nightly.discover(), nightly.BUDGET)

    assert skipped == []
    assert sum(suite.calls for suite in taken) <= nightly.BUDGET


def test_the_worst_metric_is_the_lowest_failing_one_not_the_lowest_one() -> None:
    """A threshold is somebody's judgement: 0.95 under a 0.99 bar beats 0.60 over a 0.50 one."""
    metrics = [
        {"metric": "passing but low", "score": 0.60, "passed": 2, "failed": 0},
        {"metric": "failing but high", "score": 0.95, "passed": 1, "failed": 1},
    ]

    assert report.worst(metrics)["metric"] == "failing but high"


def test_with_nothing_failing_the_worst_metric_is_the_lowest_score() -> None:
    """A green night still names the metric closest to its threshold."""
    metrics = [
        {"metric": "high", "score": 0.99, "passed": 2, "failed": 0},
        {"metric": "low", "score": 0.71, "passed": 2, "failed": 0},
    ]

    assert report.worst(metrics)["metric"] == "low"


def test_a_flaky_pass_over_a_failed_metric_is_still_red() -> None:
    """DeepEval exits 0 on a flaky wire case, so the scores decide the night and not pytest."""
    failed = [{"metric": "Keeps the register", "score": 0.0, "passed": 0, "failed": 1}]

    status, detail = nightly.status_of(0, failed)

    assert status == "failed"
    assert "flaky" in detail


def test_a_suite_that_passed_everything_is_green() -> None:
    """The only green there is: the child exited 0 and every verdict cleared its threshold."""
    assert nightly.status_of(0, [{"metric": "m", "score": 1.0, "passed": 2, "failed": 0}]) == (
        "done",
        None,
    )


def test_a_suite_killed_at_the_deadline_says_so() -> None:
    """A hung judge is a failure with its own reason, not a mystery exit code."""
    status, detail = nightly.status_of(None, [], deadline_s=1200)

    assert status == "failed"
    assert "1200s" in detail


def test_deepevals_own_json_is_what_the_scores_are_read_from(tmp_path) -> None:
    """Reading the file DeepEval wrote is what keeps the page and the CLI from disagreeing."""
    (tmp_path / "test_run_20260831_040000.json").write_text(
        json.dumps(
            {
                "metricsScores": [
                    {"metric": "Consent", "scores": [1.0, 0.0], "passes": 1, "fails": 1},
                ],
                "conversationalTestCases": [{"name": "apurado", "success": False, "turns": []}],
                "evaluationCost": 0.0123,
            }
        )
    )

    metrics, cases, cost = nightly.scored(tmp_path)

    assert metrics == [{"metric": "Consent", "score": 0.5, "passed": 1, "failed": 1}]
    assert [case["name"] for case in cases] == ["apurado"]
    assert cost == pytest.approx(0.0123)


def test_a_suite_that_scored_nothing_is_not_an_error(tmp_path) -> None:
    """A crash before the first judge leaves no file; the status already says it failed."""
    assert nightly.scored(tmp_path) == ([], [], 0.0)


def test_the_index_gets_its_header_once_and_a_line_per_night(tmp_path) -> None:
    """`tmp/evals/index.tsv` is the whole history of the habit, appended to and never rewritten."""
    index = tmp_path / "index.tsv"
    page_at = nightly.OUT / "2026-08-31" / "index.html"
    row = report.index_row("2026-08-31", _result().view(), page_at)

    report.append_index(index, [row])
    report.append_index(index, [row])

    lines = index.read_text().splitlines()
    assert lines[0].split("\t") == list(report.COLUMNS)
    assert len(lines) == 3
    assert lines[1].split("\t")[:5] == ["2026-08-31", "tienda-sur/pedidos", "failed", "3", "1"]


def test_the_page_puts_the_red_metric_next_to_what_was_said() -> None:
    """A score with no transcript sends a person back to the log; this is a bug report."""
    html = page(
        date="2026-08-31",
        git="abc1234",
        budget=8,
        spent=2,
        suites=[_result().view()],
        skipped=[{"id": "clinica-norte/reagendamiento", "calls": 2}],
    )

    assert "Nunca reservó sin confirmar" in html
    assert "quiero cancelarlo" in html
    assert "Skipped by the budget" in html
    assert "clinica-norte/reagendamiento (2 calls)" in html


def _suite(tenant: str, calls: int, project: str = "p") -> Suite:
    return Suite(tenant=tenant, project=project, target=nightly.OUT / "x.py", calls=calls)


def _result() -> Result:
    return Result(
        suite=_suite("tienda-sur", calls=2, project="pedidos"),
        status="failed",
        seconds=97.4,
        metrics=[{"metric": "Consent", "score": 0.5, "passed": 3, "failed": 1}],
        cases=[
            {
                "name": "apurado-cancela-el-pedido",
                "success": False,
                "metricsData": [
                    {
                        "name": "Consent",
                        "threshold": 1.0,
                        "success": False,
                        "score": 0.0,
                        "reason": "Nunca reservó sin confirmar",
                    }
                ],
                "turns": [{"role": "user", "content": "quiero cancelarlo"}],
            }
        ],
        judge_usd=0.0123,
        detail="the suite exited 1 — read the log",
    )
