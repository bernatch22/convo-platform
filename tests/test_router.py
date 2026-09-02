"""resolve: four sources can name the tenant; the first wins; a broken tenant is not fatal."""

import pathlib
import textwrap

import pytest

from convo.session import registry, router
from convo.state.store import MemoryStore, ProjectVersion, Route
from convo.testing.fake_job import fake_job_context

pytestmark = pytest.mark.unit

META = '{"tenant": "clinica-norte", "project": "reagendamiento", "channel": "voice"}'


@pytest.fixture
def store() -> MemoryStore:
    store = MemoryStore()
    store.add_route(Route("cc", "+34910000000", "clinica-norte", "reagendamiento", "voice"))
    return store


@pytest.fixture(autouse=True)
def console_env(monkeypatch):
    monkeypatch.delenv("TENANT", raising=False)
    monkeypatch.delenv("PROJECT", raising=False)
    monkeypatch.setenv("FLEET", "cc")


async def test_dispatch_metadata_names_tenant_project_and_channel(store) -> None:
    tc = await router.resolve(fake_job_context(metadata=META), store)

    assert (tc.tenant.id, tc.project.id, tc.channel) == ("clinica-norte", "reagendamiento", "voice")
    assert tc.log is not None and tc.tools is not None


async def test_dispatch_attributes_name_the_tenant_for_a_web_room(store) -> None:
    ctx = fake_job_context(attributes={"convo.tenant": "clinica-norte", "convo.channel": "chat"})

    tc = await router.resolve(ctx, store)

    assert (tc.tenant.id, tc.project.id, tc.channel) == ("clinica-norte", "reagendamiento", "chat")


async def test_a_sip_call_is_routed_by_the_number_it_dialled(store) -> None:
    ctx = fake_job_context(participant_attributes={"sip.trunkPhoneNumber": "+34910000000"})

    tc = await router.resolve(ctx, store)

    assert (tc.tenant.id, tc.channel) == ("clinica-norte", "voice")


async def test_a_phone_call_is_a_room_job_and_the_caller_is_found_in_the_room(store) -> None:
    ctx = fake_job_context(room_participants={"sip.trunkPhoneNumber": "+34910000000"})

    tc = await router.resolve(ctx, store)

    assert (tc.tenant.id, tc.channel) == ("clinica-norte", "voice")


async def test_the_sip_attributes_of_the_call_are_written_on_session_start(store) -> None:
    dialled = {"sip.trunkPhoneNumber": "+34910000000", "sip.callID": "TW-1"}

    tc = await router.resolve(fake_job_context(room_participants=dialled), store)

    assert tc.log.events()[0].payload["sip"] == dialled


async def test_a_number_without_a_route_is_unroutable(store) -> None:
    ctx = fake_job_context(participant_attributes={"sip.trunkPhoneNumber": "+34999999999"})

    with pytest.raises(router.UnroutableTenant, match="no route"):
        await router.resolve(ctx, store)


async def test_the_console_falls_back_to_the_environment_as_a_voice_session(
    store, monkeypatch
) -> None:
    monkeypatch.setenv("TENANT", "clinica-norte")
    monkeypatch.setenv("PROJECT", "reagendamiento")

    tc = await router.resolve(fake_job_context(), store)

    assert tc.tenant.id == "clinica-norte" and tc.channel == "voice"


async def test_an_unknown_tenant_is_refused_with_the_known_list(store) -> None:
    ctx = fake_job_context(metadata='{"tenant": "nadie", "project": "x"}')

    with pytest.raises(router.UnroutableTenant, match="known: \\['clinica-norte'"):
        await router.resolve(ctx, store)


async def test_a_pinned_version_travels_into_the_context_and_the_first_event(store) -> None:
    store.pin_version(ProjectVersion("clinica-norte", "reagendamiento", "v7", "KNOWLEDGE V7"))

    tc = await router.resolve(fake_job_context(metadata=META), store)

    assert tc.project_version == "v7"
    assert tc.knowledge_override == "KNOWLEDGE V7"
    assert tc.log.events()[0].payload["project_version"] == "v7"


def test_a_broken_tenant_folder_is_unroutable_and_the_others_still_serve() -> None:
    broken = registry.TENANTS_DIR / "zz-broken-test"
    broken.mkdir()
    try:
        (broken / "__init__.py").write_text("")
        (broken / "tenant.py").write_text(textwrap.dedent('raise RuntimeError("boom")\n'))

        loaded = registry.load_registry()

        assert "clinica-norte" in loaded
        assert not any(name.startswith("zz-broken") for name in loaded)
    finally:
        for f in broken.glob("**/*"):
            if f.is_file():
                f.unlink()
        for d in sorted(broken.glob("**/"), reverse=True):
            d.rmdir()
        assert not pathlib.Path(broken).exists()
