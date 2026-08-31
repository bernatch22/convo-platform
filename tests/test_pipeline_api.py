"""The pipeline: the three providers as data, and the three fields a supervisor may change.

An override is only worth storing if the NEXT session runs with it, so the
round-trip is asserted where it matters — through `core.router.resolve`, the
one function every session (voice, chat, console) passes through.
"""

import pytest
from fastapi.testclient import TestClient

from api import app, open_store
from core import router
from core.agents import TenantAgent
from core.providers import tts
from core.state.events import Event
from core.state.store import MemoryStore, PipelineOverride, SessionRow, SQLiteStore
from core.testing.fake_job import fake_job_context

pytestmark = pytest.mark.unit

TENANT, PROJECT = "clinica-norte", "reagendamiento"
PIPELINE = f"/pipeline/{TENANT}/{PROJECT}"
META = '{"tenant": "clinica-norte", "project": "reagendamiento", "channel": "voice"}'
CAROLINA = "UOIqAnmS11Reiei1Ytkc"


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def client(store: MemoryStore) -> TestClient:
    app.dependency_overrides[open_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def console_env(monkeypatch):
    """The console's TENANT/PROJECT must not decide who `resolve` answers here."""
    monkeypatch.delenv("TENANT", raising=False)
    monkeypatch.delenv("PROJECT", raising=False)


def test_the_snapshot_names_every_provider_the_next_call_will_use(client) -> None:
    view = client.get(PIPELINE).json()

    assert view["stt"]["model"] == "stt-rt-v5"
    assert view["stt"]["language_hints"] == ["es", "en"]
    assert view["stt"]["endpointing"] == {
        "max_endpoint_delay_ms": 1000,
        "latency_adjustment_level": 2,
        "sensitivity": 0.3,
    }
    assert view["llm"]["model"] == "claude-haiku-4-5" and view["llm"]["caching"] == "ephemeral"
    assert view["llm"]["cache_minimum_tokens"] == 4096, "below it, caching is a silent no-op"
    assert view["tts"]["model"] == "eleven_flash_v2_5"  # the clinic's latency profile
    assert view["tts"]["sync_alignment"] is True
    assert set(view["tts"]["forbidden_models"]) == set(tts.FORBIDDEN_MODELS)
    assert view["tts"]["voice"], "voice is project data and the console shows it"
    reasons = view["tts"]["forbidden_reasons"]
    assert set(reasons) == set(tts.FORBIDDEN_MODELS)
    for model, why in reasons.items():
        assert model in why and tts.DEFAULT_MODEL in why, "the console greys it out and says why"


def test_medians_are_measured_over_the_project_s_stored_voice_calls(client, store) -> None:
    _record_call(store, "s1", ttft=0.4, e2e=1.0)
    _record_call(store, "s2", ttft=0.6, e2e=2.0)

    latency = client.get(PIPELINE).json()["latency"]

    assert (latency["sessions"], latency["turns"]) == (2, 2)
    assert latency["medians"]["llm_node_ttft"] == 0.5
    assert latency["medians"]["e2e_latency"] == 1.5
    assert latency["medians"]["tts_node_ttfb"] is None, "never measured is null, never zero"


def test_a_project_nobody_has_called_reports_no_medians(client) -> None:
    latency = client.get(PIPELINE).json()["latency"]

    assert latency["sessions"] == 0 and all(v is None for v in latency["medians"].values())


async def test_a_put_changes_what_the_next_session_resolves_to(client, store) -> None:
    body = {"voice": CAROLINA, "tts_model": tts.LATENCY_MODEL, "greeting": "Clínica Norte, dígame."}

    reply = client.put(PIPELINE, json=body).json()

    assert reply["tts"]["voice"] == CAROLINA and reply["tts"]["model"] == tts.LATENCY_MODEL
    assert reply["greeting"] == "Clínica Norte, dígame."
    tc = await router.resolve(fake_job_context(metadata=META), store)
    assert tc.project.voice == CAROLINA, "the next session speaks with the console's voice"
    assert tc.project.tts_model == tts.LATENCY_MODEL
    assert tc.project.greeting == "Clínica Norte, dígame."


async def test_a_project_with_no_override_resolves_exactly_as_git_deployed_it(store) -> None:
    tc = await router.resolve(fake_job_context(metadata=META), store)

    assert tc.project.greeting.startswith("Clínica Norte")  # git ships one since ms-10
    assert tc.project.tts_model == "eleven_flash_v2_5"


def test_a_forbidden_tts_model_is_refused_with_the_rule_that_refuses_it(client, store) -> None:
    reply = client.put(PIPELINE, json={"tts_model": "eleven_v3"})

    assert reply.status_code == 422
    detail = reply.json()["detail"]
    assert "eleven_v3" in detail and "not realtime" in detail
    assert tts.DEFAULT_MODEL in detail, "a refusal names what to use instead"
    assert store.pipeline_overrides(TENANT, PROJECT) == [], "nothing forbidden reaches the store"


def test_the_deprecated_turbo_model_is_refused_too(client) -> None:
    reply = client.put(PIPELINE, json={"tts_model": "eleven_turbo_v2_5"})

    assert reply.status_code == 422 and "deprecated" in reply.json()["detail"]


def test_an_unknown_field_and_an_empty_body_are_both_refused(client) -> None:
    assert client.put(PIPELINE, json={"ttsModel": "eleven_flash_v2_5"}).status_code == 422
    assert client.put(PIPELINE, json={"model": "x"}).status_code == 422
    assert client.put(PIPELINE, json={}).status_code == 422


def test_an_unknown_tenant_or_project_is_a_404_naming_what_exists(client) -> None:
    assert "clinica-norte" in client.get("/pipeline/acme/x").json()["detail"]
    assert client.get(f"/pipeline/{TENANT}/x").status_code == 404


def test_an_override_survives_the_process_in_sqlite(tmp_path) -> None:
    path = tmp_path / "convo.db"
    SQLiteStore(path).set_pipeline_override(PipelineOverride(TENANT, PROJECT, "voice", CAROLINA))

    rows = SQLiteStore(path).pipeline_overrides(TENANT, PROJECT)

    assert [(row.field, row.value) for row in rows] == [("voice", CAROLINA)]
    assert rows[0].updated_at > 0, "the console shows when a field was last touched"


def test_setting_a_field_twice_leaves_one_row(client, store) -> None:
    client.put(PIPELINE, json={"voice": "first"})
    view = client.put(PIPELINE, json={"voice": "second"}).json()

    assert [o["value"] for o in view["overrides"]] == ["second"]


async def test_the_stored_greeting_is_the_sentence_the_call_opens_with(store) -> None:
    """The last link: an override that resolves is only worth storing if the caller hears it."""
    store.set_pipeline_override(PipelineOverride(TENANT, PROJECT, "greeting", "Clínica Norte."))
    tc = await router.resolve(fake_job_context(metadata=META), store)
    session = _FakeSession()

    await _Stage(tc, session).on_enter()

    assert session.said == "Clínica Norte.", "the console's words, not a paraphrase of them"
    assert not session.generated, "the opening line is not generated when it is written"


async def test_without_a_greeting_the_entry_stage_still_generates_its_opening(store) -> None:
    import dataclasses

    tc = await router.resolve(fake_job_context(metadata=META), store)
    tc.project = dataclasses.replace(tc.project, greeting="")  # git ships one; blank it here
    session = _FakeSession()

    await _Stage(tc, session).on_enter()

    assert session.said is None and session.generated


class _FakeSession:
    """The two calls `on_enter` can make, recorded instead of spoken."""

    def __init__(self) -> None:
        self.said: str | None = None
        self.generated = False

    def say(self, text: str, **kwargs) -> None:
        self.said = text

    def generate_reply(self) -> None:
        self.generated = True


class _Stage(TenantAgent):
    """A stage attached to a fake session: `Agent.session` needs a running activity, we do not."""

    def __init__(self, tc, session: _FakeSession) -> None:
        super().__init__(tc, instructions="prueba")
        self._fake = session

    @property
    def session(self) -> _FakeSession:
        return self._fake


def _record_call(store: MemoryStore, session_id: str, ttft: float, e2e: float) -> None:
    """One stored voice call of the project, with a single measured agent turn."""
    store.open_session(SessionRow(session_id, TENANT, PROJECT, "voice", started_at=1.0))
    metrics = {"llm_node_ttft": ttft, "e2e_latency": e2e}
    store.append(session_id, Event(1, "turn.agent", 1000, {"text": "sí", "metrics": metrics}))
