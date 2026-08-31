"""Providers are data before they are connections: every option is asserted without a network."""

import dataclasses

import pytest
from livekit.plugins import deepgram

from core.context import Project
from core.providers import stt, tts, turn
from core.testing import fake_context

pytestmark = pytest.mark.unit


@pytest.fixture
def project() -> Project:
    """A copy: the registry's project is a singleton and tests below change its voice and model."""
    return dataclasses.replace(fake_context("clinica-norte", "reagendamiento").project)


# --- Soniox ------------------------------------------------------------------


def test_soniox_runs_v5_with_the_voice_agent_endpointing_profile(project: Project) -> None:
    options = stt.stt_options(project)

    assert options.model == "stt-rt-v5"
    assert options.language_hints == ["es", "en"]
    assert options.sample_rate == 16000
    assert options.max_endpoint_delay_ms == 1000
    assert options.endpoint_latency_adjustment_level == 2
    assert options.endpoint_sensitivity == 0.3


def test_the_project_vocabulary_travels_as_context_terms(project: Project) -> None:
    project.keyterms = ["Clínica Norte", "Dra. Campos", "traumatología"]

    options = stt.stt_options(project)

    assert options.context is not None
    assert options.context.terms == ["Clínica Norte", "Dra. Campos", "traumatología"]


def test_without_a_soniox_key_there_is_no_stt(project: Project, monkeypatch) -> None:
    monkeypatch.delenv(stt.KEY_ENV, raising=False)
    tc = fake_context("clinica-norte", "reagendamiento")

    assert stt.stt_for(tc.tenant, project) is None


def test_with_a_key_soniox_is_built_with_those_options(project: Project, monkeypatch) -> None:
    monkeypatch.setenv(stt.KEY_ENV, "sx-test")
    tc = fake_context("clinica-norte", "reagendamiento")

    built = stt.stt_for(tc.tenant, project)

    assert built is not None and built.model == "stt-rt-v5"
    assert built._params.endpoint_sensitivity == 0.3


# --- Deepgram Flux -----------------------------------------------------------


def test_flux_runs_the_multilingual_model_because_the_english_one_refuses_a_hint(
    project: Project,
) -> None:
    options = stt.deepgram_options(project)

    assert options["model"] == "flux-general-multi"
    assert options["language_hint"] == ["es", "en"]
    assert options["sample_rate"] == 16000
    assert options["eot_threshold"] == 0.7
    assert options["eot_timeout_ms"] == 1000


def test_the_project_vocabulary_travels_as_flux_keyterms(project: Project) -> None:
    project.keyterms = ["Clínica Norte", "Dra. Campos"]

    assert stt.deepgram_options(project)["keyterm"] == ["Clínica Norte", "Dra. Campos"]


def test_choosing_deepgram_builds_flux_and_never_touches_soniox(
    project: Project, monkeypatch
) -> None:
    monkeypatch.setenv(stt.DEEPGRAM_KEY_ENV, "dg-test")
    monkeypatch.setenv(stt.KEY_ENV, "sx-test")
    project.stt_provider = "deepgram"
    tc = fake_context("clinica-norte", "reagendamiento")

    built = stt.stt_for(tc.tenant, project)

    assert isinstance(built, deepgram.STTv2), "the /v2/listen class, not the nova-3 one"
    assert built.model == "flux-general-multi"
    assert built._opts.language_hint == ["es", "en"]
    assert built._opts.eot_threshold == 0.7


def test_without_a_deepgram_key_the_chosen_provider_still_yields_no_stt(
    project: Project, monkeypatch
) -> None:
    monkeypatch.delenv(stt.DEEPGRAM_KEY_ENV, raising=False)
    monkeypatch.setenv(stt.KEY_ENV, "sx-test")
    project.stt_provider = "deepgram"
    tc = fake_context("clinica-norte", "reagendamiento")

    assert stt.stt_for(tc.tenant, project) is None, "a key it does not have is not a fallback"


@pytest.mark.parametrize("named", ["whisper", "", "SONIOX"])
def test_a_provider_the_platform_does_not_have_falls_back_to_the_default(
    project: Project, named
) -> None:
    project.stt_provider = named

    assert stt.provider_for(project) == "soniox"


def test_the_default_project_is_still_heard_by_soniox(project: Project) -> None:
    assert project.stt_provider == "soniox"
    assert stt.provider_for(project) == "soniox"


# --- ElevenLabs --------------------------------------------------------------


def test_the_clinic_opts_into_the_latency_profile_after_the_pstn_measurements(
    project: Project,
) -> None:
    assert tts.tts_model(project) == "eleven_flash_v2_5"


def test_the_platform_default_is_still_conversational_v3(project: Project) -> None:
    project.tts_model = None

    assert tts.tts_model(project) == "eleven_v3_conversational"


@pytest.mark.parametrize("wanted", ["eleven_turbo_v2_5", "eleven_v3"])
def test_the_deprecated_and_non_realtime_models_are_never_chosen(project: Project, wanted) -> None:
    project.tts_model = wanted

    assert tts.tts_model(project) == "eleven_v3_conversational"


def test_a_project_may_opt_into_the_latency_profile(project: Project) -> None:
    project.tts_model = tts.LATENCY_MODEL

    assert tts.tts_model(project) == "eleven_flash_v2_5"


def test_with_a_key_the_voice_is_the_projects_and_alignment_is_on(
    project: Project, monkeypatch
) -> None:
    monkeypatch.setenv(tts.KEY_ENV, "el-test")
    tc = fake_context("clinica-norte", "reagendamiento")

    built = tts.tts_for(tc.tenant, project)

    assert built is not None
    assert built._opts.voice_id == "UOIqAnmS11Reiei1Ytkc"
    assert built._opts.model == "eleven_flash_v2_5"
    assert built._opts.sync_alignment is True
    assert built._opts.language == "es"


def test_without_a_key_or_a_voice_there_is_no_tts(project: Project, monkeypatch) -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    monkeypatch.delenv(tts.KEY_ENV, raising=False)
    assert tts.tts_for(tc.tenant, project) is None

    monkeypatch.setenv(tts.KEY_ENV, "el-test")
    project.voice = None
    assert tts.tts_for(tc.tenant, project) is None


# --- turn taking -------------------------------------------------------------


def test_the_vad_keeps_the_minimum_silence_the_session_accepts() -> None:
    vad = turn.vad_for()

    assert vad._opts.min_silence_duration >= 0.25


def test_the_turn_detector_is_the_local_mini_model() -> None:
    detector = turn.turn_detector_for()

    assert "mini" in detector.model
