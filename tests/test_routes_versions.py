"""routes and project_versions: the two small tables the router reads, in both stores."""

import pytest

from core.state.store import MemoryStore, ProjectVersion, Route, SQLiteStore

pytestmark = pytest.mark.unit


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    return MemoryStore() if request.param == "memory" else SQLiteStore(tmp_path / "convo.db")


def test_a_route_is_found_by_fleet_and_key_and_replaced_on_re_add(store) -> None:
    store.add_route(Route("cc", "+34910000000", "clinica-norte", "reagendamiento"))
    store.add_route(Route("cc", "+34910000000", "clinica-norte", "reagendamiento", "chat"))

    found = store.route("cc", "+34910000000")

    assert found is not None and found.channel == "chat"
    assert store.route("other", "+34910000000") is None
    assert len(store.routes()) == 1


def test_a_pin_replaces_the_previous_one_and_keeps_its_override(store) -> None:
    store.pin_version(ProjectVersion("clinica-norte", "reagendamiento", "v1"))
    store.pin_version(ProjectVersion("clinica-norte", "reagendamiento", "v2", "OVERRIDE"))

    pin = store.pinned_version("clinica-norte", "reagendamiento")

    assert pin is not None and (pin.version, pin.knowledge_override) == ("v2", "OVERRIDE")
    assert pin.created_at > 0 or isinstance(store, MemoryStore)
    assert store.pinned_version("clinica-norte", "otro") is None
    assert [v.version for v in store.versions()] == ["v2"]
