"""The phone line as project data: what the console may claim about a number, and what it may not.

The bug this file pins down is a UI one with a data cause: the console printed
the fleet's only number in its chrome, so a project that nobody can call looked
reachable. The fix is that the number is read per project from the same
`routes` table the router resolves a call with — so the two can never disagree.
"""

import pytest

from convo.state.store import MemoryStore, Route
from convo.telephony import lines

pytestmark = pytest.mark.unit

CLINICA, REAGENDAMIENTO = "clinica-norte", "reagendamiento"
TIENDA, PEDIDOS = "tienda-sur", "pedidos"
NUMBER = "+14176743169"


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture(autouse=True)
def fleet(monkeypatch) -> None:
    monkeypatch.setenv("FLEET", "cc")


def test_the_seed_is_the_dispatch_rule_that_exists_today(store) -> None:
    written = lines.seed(store)

    assert [(r.key, r.tenant, r.project) for r in written] == [(NUMBER, CLINICA, REAGENDAMIENTO)]
    assert store.route("cc", NUMBER) == Route("cc", NUMBER, CLINICA, REAGENDAMIENTO, "voice")


def test_seeding_twice_writes_nothing_the_second_time(store) -> None:
    lines.seed(store)

    assert lines.seed(store) == []
    assert len(store.routes()) == 1


def test_the_seed_never_overwrites_what_the_operator_stored(store) -> None:
    store.add_route(Route("cc", NUMBER, TIENDA, PEDIDOS, "voice"))

    assert lines.seed(store) == []
    assert store.route("cc", NUMBER).tenant == TIENDA, "the box is the truth, not this file"


def test_a_project_with_a_line_shows_the_number_it_is_reached_on(store) -> None:
    lines.seed(store)

    view = lines.view(store, CLINICA, REAGENDAMIENTO)

    assert view["fleet"] == "cc"
    assert view["lines"] == [{"number": NUMBER, "fleet": "cc", "channel": "voice", "serving": True}]
    assert "dispatch rule" in view["note"]


def test_a_project_with_no_line_says_so_instead_of_borrowing_the_fleets(store) -> None:
    lines.seed(store)

    view = lines.view(store, TIENDA, PEDIDOS)

    assert view["lines"] == []
    assert view["note"] == lines.NO_LINE
    assert NUMBER not in view["note"], "the clinic's number is not this project's number"


def test_a_number_registered_against_another_fleet_is_shown_as_unreachable(store) -> None:
    store.add_route(Route("other", "+34910000000", TIENDA, PEDIDOS, "voice"))

    view = lines.view(store, TIENDA, PEDIDOS)

    assert view["lines"][0]["serving"] is False
    assert "never reach this process" in view["note"]


def test_the_pipeline_snapshot_carries_the_project_s_own_phone_block(store) -> None:
    from convo.session.pipeline import snapshot
    from convo.session.registry import load_registry

    lines.seed(store)
    tenant = load_registry()[CLINICA]
    view = snapshot(tenant, tenant.projects[REAGENDAMIENTO], store)

    assert view["phone"]["lines"][0]["number"] == NUMBER
