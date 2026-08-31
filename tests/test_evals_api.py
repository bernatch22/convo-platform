"""Evals on the console: a run files itself, the next is diffed against it, one runs at a time.

The subprocess is real in every test here — a fake command, not a fake process.
"One at a time" and "killed at the deadline" are properties of a real child, and
a mock would assert nothing about either. What is faked is only what the child
runs: a python one-liner that writes the same `test_run_*.json` deepeval writes,
so the fast ring stays offline and nothing here spends a token.
"""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import app, evals_runner, open_store
from core.evals import suites
from core.evals.runner import EvalRunner
from core.state.store import MemoryStore

pytestmark = pytest.mark.unit

TENANT, PROJECT = "clinica-norte", "reagendamiento"
LAUNCH = {"tenant": TENANT, "project": PROJECT, "suite": "ring1"}

# Three stand-ins for `deepeval test run`, as python source the child executes.
FAKE_SUITE = """
import json, os, pathlib
print('running the fake suite', flush=True)
out = pathlib.Path(os.environ['DEEPEVAL_RESULTS_FOLDER'])
out.mkdir(parents=True, exist_ok=True)
scores = {'metric': 'reception_line', 'scores': [0.8, 0.9, 0.85], 'passes': 2, 'fails': 1,
          'errors': 0}
(out / 'test_run_20260101_000000.json').write_text(json.dumps({'metricsScores': [scores]}))
"""
CHATTY_SUITE = "print('the suite is talking', flush=True)\nimport time; time.sleep(1)\n"
SLOW_SUITE = "print('the suite hung', flush=True)\nimport time; time.sleep(30)\n"


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def runner(store: MemoryStore, tmp_path: Path) -> EvalRunner:
    """A runner whose `deepeval` is `python -c`: the process is real, the suite is not."""
    return EvalRunner(
        lambda: store,
        launcher=lambda target: ["python3", "-c", target],
        deadline_s=10.0,
        log_dir=tmp_path / "evals",
    )


@pytest.fixture
def client(store: MemoryStore, runner: EvalRunner) -> TestClient:
    """The app on ONE event loop for the whole test: a background run outlives its request."""
    app.dependency_overrides[open_store] = lambda: store
    app.dependency_overrides[evals_runner] = lambda: runner
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def fake_suite(monkeypatch) -> None:
    """Every project declares one suite, and it is a python snippet instead of a pytest path."""
    monkeypatch.setattr(suites, "declared", lambda *_: {"ring1": FAKE_SUITE})


def test_a_filed_run_appears_in_the_list_with_its_scores(client) -> None:
    file_run(client, [{"metric": "reception_line", "score": 0.82, "passed": 5, "failed": 1}])

    rows = client.get("/evals/runs").json()

    assert len(rows) == 1
    assert (rows[0]["tenant"], rows[0]["suite"], rows[0]["status"]) == (TENANT, "ring1", "done")
    assert rows[0]["metrics"] == [
        {"metric": "reception_line", "score": 0.82, "passed": 5, "failed": 1, "delta": None}
    ]


def test_the_second_run_of_a_suite_is_diffed_per_metric_against_the_first(client) -> None:
    file_run(client, [{"metric": "reception_line", "score": 0.70, "passed": 4, "failed": 2}])
    second = file_run(client, [{"metric": "reception_line", "score": 0.90, "passed": 6}])

    assert second["metrics"][0]["delta"] == pytest.approx(0.20)
    assert second["previous"] is not None

    newest, oldest = client.get("/evals/runs").json()
    assert newest["metrics"][0]["delta"] == pytest.approx(0.20)
    assert oldest["metrics"][0]["delta"] is None, "the first run has nothing to improve on"


def test_a_run_of_another_suite_is_never_diffed_against_this_one(client) -> None:
    file_run(client, [{"metric": "reception_line", "score": 0.70}], suite="ring1")
    other = file_run(client, [{"metric": "reception_line", "score": 0.30}], suite="personas")

    assert other["metrics"][0]["delta"] is None and other["previous"] is None


def test_the_runs_list_narrows_by_tenant_project_and_suite(client) -> None:
    file_run(client, [], suite="ring1")
    file_run(client, [], suite="personas")

    assert len(client.get("/evals/runs?suite=personas").json()) == 1
    assert len(client.get(f"/evals/runs?tenant={TENANT}").json()) == 2
    assert client.get("/evals/runs?project=nobody").json() == []


def test_a_launched_run_lands_in_the_list_with_the_scores_deepeval_wrote(client, fake_suite):
    started = client.post("/evals/run", json=LAUNCH)

    assert started.status_code == 200, started.text
    assert started.json()["status"] == "running"

    finished = wait_for(client, started.json()["id"])
    assert finished["status"] == "done"
    assert finished["metrics"] == [
        {"metric": "reception_line", "score": 0.85, "passed": 2, "failed": 1, "delta": None}
    ]
    assert [row["id"] for row in client.get("/evals/runs").json()] == [started.json()["id"]]


def test_a_second_launched_run_is_diffed_against_the_first(client, fake_suite) -> None:
    wait_for(client, client.post("/evals/run", json=LAUNCH).json()["id"])
    second = wait_for(client, client.post("/evals/run", json=LAUNCH).json()["id"])

    assert second["metrics"][0]["delta"] == pytest.approx(0.0), "the same suite scored the same"
    assert second["previous"] is not None


def test_the_log_tail_is_readable_while_the_run_is_still_going(client, monkeypatch) -> None:
    monkeypatch.setattr(suites, "declared", lambda *_: {"ring1": CHATTY_SUITE})

    run_id = client.post("/evals/run", json=LAUNCH).json()["id"]
    talking = poll(client, run_id, lambda view: view["log"])

    assert talking["status"] == "running" and talking["busy"] is True
    assert any("the suite is talking" in line for line in talking["log"])
    assert wait_for(client, run_id)["status"] == "done"


def test_this_box_runs_one_eval_at_a_time_and_refuses_the_second(client, runner, monkeypatch):
    monkeypatch.setattr(suites, "declared", lambda *_: {"ring1": SLOW_SUITE})
    runner.deadline_s = 0.4

    first = client.post("/evals/run", json=LAUNCH)
    second = client.post("/evals/run", json=LAUNCH)

    assert first.status_code == 200
    assert second.status_code == 409
    assert "one at a time" in second.json()["detail"]
    wait_for(client, first.json()["id"])


def test_a_run_past_the_deadline_is_killed_and_stored_as_failed(client, runner, monkeypatch):
    monkeypatch.setattr(suites, "declared", lambda *_: {"ring1": SLOW_SUITE})
    runner.deadline_s = 0.4

    run_id = client.post("/evals/run", json=LAUNCH).json()["id"]

    finished = wait_for(client, run_id)
    assert finished["status"] == "failed"
    assert "killed after" in finished["detail"]
    assert finished["busy"] is False, "the slot is free again"


def test_a_suite_the_project_never_declared_is_a_404_naming_the_ones_it_did(client) -> None:
    response = client.post("/evals/run", json={**LAUNCH, "suite": "made-up"})

    assert response.status_code == 404
    assert "ring1" in response.json()["detail"]


def test_every_routable_project_says_which_suites_it_declares(client) -> None:
    rows = client.get("/evals/suites").json()

    clinic = next(r for r in rows if (r["tenant"], r["project"]) == (TENANT, PROJECT))
    assert "ring1" in clinic["suites"] and clinic["name"]


def test_an_unknown_run_id_is_a_404(client) -> None:
    assert client.get("/evals/run/ev-nope").status_code == 404


def test_a_tenant_id_that_could_escape_the_tenants_folder_declares_nothing() -> None:
    assert suites.declared("../../etc", "passwd") == {}
    assert suites.declared(TENANT, PROJECT), "a real project still resolves"


def file_run(client: TestClient, metrics: list[dict], suite: str = "ring1") -> dict:
    """File one finished run the way `core.testing.report` and CI do."""
    body = {"tenant": TENANT, "project": PROJECT, "suite": suite, "metrics": metrics}
    response = client.post("/evals/runs", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def poll(client: TestClient, run_id: str, until, timeout_s: float = 15.0) -> dict:
    """Poll `GET /evals/run/<id>` the way the console does, until `until` is happy."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        view = client.get(f"/evals/run/{run_id}").json()
        if until(view):
            return view
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} never got there")


def wait_for(client: TestClient, run_id: str) -> dict:
    """Poll until the run stops saying it is running."""
    return poll(client, run_id, lambda view: view["status"] != "running")
