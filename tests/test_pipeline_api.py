"""The pipeline: the three providers as data, and the three fields a supervisor may change.

An override is only worth storing if the NEXT session runs with it, so the
round-trip is asserted where it matters — through `core.router.resolve`, the
one function every session (voice, chat, console) passes through.
"""

import os

import pytest
from fastapi.testclient import TestClient

from convo.agents import TenantAgent
from convo.api.app import app, open_store
from convo.providers import llm, stt, tts
from convo.session import router
from convo.state.events import Event
from convo.state.store import MemoryStore, PipelineOverride, SessionRow, SQLiteStore
from convo.testing.fake_job import fake_job_context

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

    assert view["stt"]["provider"] == "soniox"
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


async def test_a_put_switches_the_ear_the_next_session_opens(client, store, monkeypatch) -> None:
    monkeypatch.setenv(stt.DEEPGRAM_KEY_ENV, "dg-test")

    reply = client.put(PIPELINE, json={"stt_provider": "deepgram"}).json()

    assert reply["stt"]["provider"] == "deepgram"
    assert reply["stt"]["model"] == "flux-general-multi"
    assert reply["stt"]["endpointing"] == {
        "eot_threshold": 0.7,
        "eot_timeout_ms": 1000,
        "eager_eot_threshold": None,
    }, "Flux's own dials, not Soniox's under Flux's name"
    tc = await router.resolve(fake_job_context(metadata=META), store)
    assert tc.project.stt_provider == "deepgram", "the next session hears through Flux"
    assert stt.provider_for(tc.project) == "deepgram"


def test_the_snapshot_names_the_ears_a_supervisor_may_switch_between(client, monkeypatch) -> None:
    monkeypatch.setenv(stt.KEY_ENV, "sx-test")
    monkeypatch.delenv(stt.DEEPGRAM_KEY_ENV, raising=False)

    view = client.get(PIPELINE).json()

    assert view["stt"]["providers"] == ["soniox", "deepgram"]
    assert view["stt"]["requested_provider"] == "soniox"
    assert "stt_provider" in view["overridable"]
    greyed = view["stt"]["unavailable_reasons"]
    assert set(greyed) == {"deepgram"}, "this box has no Flux key; Soniox is the one it can open"
    assert stt.DEEPGRAM_KEY_ENV in greyed["deepgram"], "the console greys it out and says why"


def test_an_ear_this_host_has_no_key_for_is_refused_naming_the_variable(
    client, store, monkeypatch
) -> None:
    """api.py runs ON the box, so it is the one place that can answer 'is the key here?'."""
    monkeypatch.delenv(stt.DEEPGRAM_KEY_ENV, raising=False)

    reply = client.put(PIPELINE, json={"stt_provider": "deepgram"})

    assert reply.status_code == 422
    detail = reply.json()["detail"]
    assert "deepgram" in detail and stt.DEEPGRAM_KEY_ENV in detail
    assert store.pipeline_overrides(TENANT, PROJECT) == [], "the door held: nothing was stored"


def test_an_stt_provider_the_platform_does_not_run_is_refused_with_both_names(
    client, store
) -> None:
    reply = client.put(PIPELINE, json={"stt_provider": "whisper"})

    assert reply.status_code == 422
    detail = reply.json()["detail"]
    assert "whisper" in detail and "soniox" in detail and "deepgram" in detail
    assert store.pipeline_overrides(TENANT, PROJECT) == [], "nothing unknown reaches the store"


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


CAROLINA_RUIZ = "h2cd3gvcqTp3m65Dysk7"


def test_an_empty_voice_is_refused_before_it_can_mute_the_next_call(client, store) -> None:
    reply = client.put(PIPELINE, json={"voice": "   "})

    assert reply.status_code == 422
    detail = reply.json()["detail"]
    assert "mute" in detail and "ELEVENLABS_API_KEY" in detail, "the refusal names the symptom"
    assert store.pipeline_overrides(TENANT, PROJECT) == [], "nothing empty reaches the store"


def test_a_pasted_voice_id_is_stored_without_its_stray_whitespace(client) -> None:
    view = client.put(PIPELINE, json={"voice": f"  {CAROLINA_RUIZ}\n"}).json()

    assert view["tts"]["voice"] == CAROLINA_RUIZ


async def test_a_voice_stored_empty_before_the_rule_cannot_silence_a_call(store) -> None:
    store.set_pipeline_override(PipelineOverride(TENANT, PROJECT, "voice", ""))

    tc = await router.resolve(fake_job_context(metadata=META), store)

    assert tc.project.voice == CAROLINA, "a blank row is ignored, not applied"
    assert tts.tts_for(tc.tenant, tc.project) is not None or "ELEVENLABS_API_KEY" not in os.environ


async def test_session_start_names_the_voice_the_call_really_spoke_with(store) -> None:
    client_put = TestClient(app)
    app.dependency_overrides[open_store] = lambda: store
    client_put.put(PIPELINE, json={"voice": CAROLINA_RUIZ})
    app.dependency_overrides.clear()

    tc = await router.resolve(fake_job_context(metadata=META), store)

    start = next(event for event in tc.log.events() if event.kind == "session.start")
    assert start.payload["pipeline"]["voice"] == CAROLINA_RUIZ
    assert start.payload["pipeline"]["tts_model"] == tts.LATENCY_MODEL
    assert start.payload["pipeline"]["llm_model"] == llm.DEFAULT_MODEL
    assert start.payload["pipeline"]["stt_provider"] == stt.SONIOX


async def test_a_chat_session_claims_no_voice_because_it_builds_none(store) -> None:
    chat = '{"tenant": "clinica-norte", "project": "reagendamiento", "channel": "chat"}'

    tc = await router.resolve(fake_job_context(metadata=chat), store)

    start = next(event for event in tc.log.events() if event.kind == "session.start")
    assert start.payload["pipeline"]["voice"] is None
    assert start.payload["pipeline"]["llm_model"] == llm.DEFAULT_MODEL, "the model still decides"


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


# --- the LLM slot ------------------------------------------------------------


def test_the_snapshot_shows_the_llm_family_its_caching_floor_and_the_whole_menu(client) -> None:
    view = client.get(PIPELINE).json()["llm"]

    assert (view["provider"], view["model"]) == ("anthropic", "claude-haiku-4-5")
    assert view["allowed_models"] == ["claude-haiku-4-5", "gpt-5.4-mini"]
    assert view["cache_minimum_tokens"] == 4096 and view["caching"] == "ephemeral"


async def test_a_put_of_the_openai_model_changes_what_the_next_session_builds(
    client, store, monkeypatch
) -> None:
    """The whole point of the slot: the console swaps the vendor and `resolve` agrees."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    reply = client.put(PIPELINE, json={"llm_model": "gpt-5.4-mini"}).json()

    assert reply["llm"] == {
        **reply["llm"],
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "caching": "automatic",
        "cache_minimum_tokens": 1024,
    }
    assert "1024" in reply["llm"]["cache_note"], "each family states its own caching story"
    tc = await router.resolve(fake_job_context(metadata=META), store)
    assert tc.project.llm_model == "gpt-5.4-mini"
    assert llm.llm_for(tc.tenant, tc.project).model == "gpt-5.4-mini"


def test_a_model_outside_the_allow_list_is_refused_with_the_list(client, store) -> None:
    reply = client.put(PIPELINE, json={"llm_model": "gpt-4o"})

    assert reply.status_code == 422
    detail = reply.json()["detail"]
    assert "gpt-4o" in detail
    for allowed in llm.ALLOWED_MODELS:
        assert allowed in detail, "a refusal names every model that would have been accepted"
    assert store.pipeline_overrides(TENANT, PROJECT) == [], "nothing unpriced reaches the store"


def test_a_model_this_host_has_no_key_for_is_refused_naming_the_variable(
    client, store, monkeypatch
) -> None:
    """The live incident, at the door: `gpt-5.4-mini` is priced and legal — and unrunnable here."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    reply = client.put(PIPELINE, json={"llm_model": "gpt-5.4-mini"})

    assert reply.status_code == 422
    detail = reply.json()["detail"]
    assert "gpt-5.4-mini" in detail and "OPENAI_API_KEY" in detail
    assert llm.DEFAULT_MODEL in detail, "a refusal says what the project stays on"
    assert store.pipeline_overrides(TENANT, PROJECT) == [], "the door held: nothing was stored"


async def test_an_override_stored_before_the_key_vanished_still_builds_a_session(
    client, store, monkeypatch
) -> None:
    """The net under the door: the row outlives the key, and the project stays on the air."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert client.put(PIPELINE, json={"llm_model": "gpt-5.4-mini"}).status_code == 200
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    tc = await router.resolve(fake_job_context(metadata=META), store)

    assert tc.project.llm_model == "gpt-5.4-mini", "the stored row is untouched"
    assert llm.llm_for(tc.tenant, tc.project).model == llm.DEFAULT_MODEL, "the call still happens"
    view = client.get(PIPELINE).json()["llm"]
    assert view["requested_model"] == "gpt-5.4-mini" and view["model"] == llm.DEFAULT_MODEL
    assert "OPENAI_API_KEY" in view["unavailable_reasons"]["gpt-5.4-mini"]


def test_every_model_the_platform_runs_has_a_price(client) -> None:
    from convo.observability.prices import PRICES

    for model in llm.ALLOWED_MODELS:
        assert model in PRICES, "the allow-list IS the priced list; they cannot drift apart"
