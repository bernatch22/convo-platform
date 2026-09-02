"""The datasets a project evaluates against, as the console reads them: off disk, per suite.

The counts here are the point of the endpoint. `ring1` says twelve because
`goldens.json` holds twelve rows and the suite parametrises over every one of
them; if somebody adds a golden and the screen keeps saying twelve, the screen
is lying about what a run just cost. So the test asserts the count against the
file rather than against a number written here.
"""

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from convo.api.app import app
from convo.evals import goldens

pytestmark = pytest.mark.unit

TENANT, PROJECT = "clinica-norte", "reagendamiento"
ROOT = pathlib.Path(__file__).resolve().parents[1]
EVALS = ROOT / "tenants" / TENANT / "projects" / PROJECT / "evals"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def suite_named(payload: dict, name: str) -> dict:
    """One suite out of the answer, so a test reads as the sentence it is checking."""
    return next(suite for suite in payload["suites"] if suite["suite"] == name)


def test_every_declared_suite_is_answered_for(client: TestClient) -> None:
    payload = client.get(f"/evals/goldens/{TENANT}/{PROJECT}").json()
    declared = set(json.loads((EVALS / "suites.json").read_text()))

    answered = {suite["suite"] for suite in payload["suites"]}
    assert declared <= answered, "a suite a project declares must be readable on screen"
    assert "ring2" in answered, "the ring-2 suite is declared by its file, not by suites.json"


def test_a_ring_one_suite_counts_the_goldens_the_run_parametrises_over(client: TestClient) -> None:
    payload = client.get(f"/evals/goldens/{TENANT}/{PROJECT}").json()
    ring1 = suite_named(payload, "ring1")

    assert ring1["kind"] == "turn"
    assert ring1["dataset"] == "goldens.json"
    assert ring1["count"] == len(json.loads((EVALS / "goldens.json").read_text()))
    assert ring1["count"] == len(ring1["goldens"])


def test_no_two_goldens_of_a_project_answer_to_the_same_name() -> None:
    """The name is the join key of the eval matrix, so two goldens cannot share one.

    `core.testing.deepeval.test_case_for` names each case after the golden's
    input, and `core.testing.matrix` joins two models' runs on that name — so a
    duplicate does not fail anything, it silently makes one row of the
    comparison table meaningless. Ms-20 nearly shipped two: a cancellation
    golden whose caller says "Ana García Ruiz" and a contact-change golden whose
    caller says exactly the same thing, told apart only by their `before`.
    """
    for dataset in ("goldens.json", "ring2_goldens.json"):
        rows = json.loads((EVALS / dataset).read_text())
        names = [row.get("input") or row.get("name") for row in rows]
        assert len(set(names)) == len(names), f"{dataset} has two goldens under one name"


def test_a_ring_one_golden_carries_the_line_the_behaviour_and_the_tools(
    client: TestClient,
) -> None:
    payload = client.get(f"/evals/goldens/{TENANT}/{PROJECT}").json()
    golden = suite_named(payload, "ring1")["goldens"][0]

    assert golden["input"]
    assert golden["expected_behaviour"]
    assert isinstance(golden["expected_tools"], list)


def test_a_ring_two_golden_carries_the_persona_the_objective_and_its_policies(
    client: TestClient,
) -> None:
    payload = client.get(f"/evals/goldens/{TENANT}/{PROJECT}").json()
    ring2 = suite_named(payload, "ring2")
    golden = ring2["goldens"][0]

    assert ring2["kind"] == "call"
    assert ring2["count"] == len(json.loads((EVALS / "ring2_goldens.json").read_text()))
    assert golden["persona"] and golden["objective"] and golden["turns"]
    assert golden["policies"], "a ring-2 golden names the hard policies it holds the call to"


def test_a_suite_whose_cases_live_in_code_says_so_instead_of_showing_none(
    client: TestClient,
) -> None:
    payload = client.get(f"/evals/goldens/{TENANT}/{PROJECT}").json()
    grounding = suite_named(payload, "grounding")

    assert grounding["kind"] == "code"
    assert grounding["count"] is None
    assert grounding["target"].endswith(".py"), "the screen points at where the cases are written"


def test_both_projects_are_readable(client: TestClient) -> None:
    for tenant, project in [(TENANT, PROJECT), ("tienda-sur", "pedidos")]:
        payload = client.get(f"/evals/goldens/{tenant}/{project}").json()
        counted = [suite for suite in payload["suites"] if suite["count"]]
        assert counted, f"{tenant}/{project} shows no case at all"


def test_an_unknown_project_is_a_404_and_never_a_directory_listing(client: TestClient) -> None:
    answer = client.get(f"/evals/goldens/{TENANT}/no-such-project")

    assert answer.status_code == 404
    assert "no-such-project" in answer.json()["detail"]
    assert "reagendamiento" not in answer.json()["detail"], "a refusal lists nothing"


@pytest.mark.parametrize("tenant", ["../..", "..", "Clinica-Norte", "", "/etc"])
def test_an_id_that_could_name_a_folder_elsewhere_is_refused(tenant: str) -> None:
    with pytest.raises(goldens.UnknownProject):
        goldens.datasets(tenant, PROJECT)


def test_the_reader_imports_no_tenant_module() -> None:
    module = pathlib.Path(goldens.__file__)
    source = module.read_text()

    assert "import tenants" not in source and "from tenants" not in source
    assert "import_module" not in source, "the datasets are read off disk, never executed"


def test_a_malformed_dataset_empties_a_suite_instead_of_breaking_the_screen(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "goldens.json").write_text("{ not json")

    assert goldens.turn_goldens(tmp_path) == []
    assert goldens.call_goldens(tmp_path) == []
