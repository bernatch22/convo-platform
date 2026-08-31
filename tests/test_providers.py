"""Providers are data before they are connections: every option is asserted without a network."""

import dataclasses
import logging
import os

import pytest
from livekit.plugins import deepgram

from core.context import Project
from core.providers import llm, stt, tts, turn
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


def test_an_ear_this_host_has_no_key_for_falls_back_to_the_default_one(
    project: Project, monkeypatch, caplog
) -> None:
    """A stored override must never leave a project deaf: Soniox hears while Flux cannot."""
    monkeypatch.delenv(stt.DEEPGRAM_KEY_ENV, raising=False)
    monkeypatch.setenv(stt.KEY_ENV, "sx-test")
    project.stt_provider = "deepgram"
    tc = fake_context("clinica-norte", "reagendamiento")

    with caplog.at_level(logging.WARNING, logger="platform.stt"):
        built = stt.stt_for(tc.tenant, project)

    assert stt.provider_for(project) == "soniox"
    assert built is not None and built.model == "stt-rt-v5"
    assert len(caplog.records) == 1, "one line, not one per turn"
    assert stt.DEEPGRAM_KEY_ENV in caplog.text and "sx-test" not in caplog.text


def test_with_neither_key_the_session_is_text_only_as_it_has_always_been(
    project: Project, monkeypatch
) -> None:
    monkeypatch.delenv(stt.DEEPGRAM_KEY_ENV, raising=False)
    monkeypatch.delenv(stt.KEY_ENV, raising=False)
    project.stt_provider = "deepgram"
    tc = fake_context("clinica-norte", "reagendamiento")

    assert stt.stt_for(tc.tenant, project) is None


def test_each_ear_names_the_variable_its_key_must_live_in(monkeypatch) -> None:
    monkeypatch.setenv(stt.DEEPGRAM_KEY_ENV, "dg-test")
    monkeypatch.delenv(stt.KEY_ENV, raising=False)

    assert stt.key_env("deepgram") == "DEEPGRAM_API_KEY"
    assert stt.key_env("soniox") == "SONIOX_API_KEY"
    assert stt.runnable("deepgram") and not stt.runnable("soniox")


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


# --- the LLM slot ------------------------------------------------------------


def test_a_project_that_names_no_model_gets_the_platform_default(project: Project) -> None:
    project.llm_model = None

    assert llm.llm_model(project) == "claude-haiku-4-5"


def test_a_project_may_opt_into_the_openai_model(project: Project) -> None:
    project.llm_model = "gpt-5.4-mini"

    assert llm.llm_model(project) == "gpt-5.4-mini"
    assert llm.family("gpt-5.4-mini") == "openai"
    assert llm.family("claude-haiku-4-5") == "anthropic"


def test_a_model_nobody_priced_is_never_built(project: Project) -> None:
    """git may name anything; the platform still only opens a connection it costed."""
    project.llm_model = "gpt-4o"

    assert llm.llm_model(project) == llm.DEFAULT_MODEL


def test_claude_is_built_with_ephemeral_caching(project: Project, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    tc = fake_context("clinica-norte", "reagendamiento")
    project.llm_model = None

    built = llm.llm_for(tc.tenant, project)

    assert built.model == "claude-haiku-4-5"
    assert built._opts.caching == "ephemeral"


def test_a_model_this_host_has_no_key_for_never_reaches_a_connection(
    project: Project, monkeypatch
) -> None:
    """The KeyError of 2026-08-31: a legal, priced model on a box without that vendor's key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    project.llm_model = "gpt-5.4-mini"

    assert llm.llm_model(project) == llm.DEFAULT_MODEL
    assert not llm.runnable("gpt-5.4-mini")
    assert llm.key_env("gpt-5.4-mini") == "OPENAI_API_KEY"
    assert llm.key_env("claude-haiku-4-5") == "ANTHROPIC_API_KEY"


def test_the_swapped_model_is_logged_once_by_its_variable_and_never_by_its_value(
    project: Project, monkeypatch, caplog
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    project.llm_model = "gpt-5.4-mini"
    tc = fake_context("clinica-norte", "reagendamiento")

    with caplog.at_level(logging.WARNING, logger="platform.llm"):
        built = llm.llm_for(tc.tenant, project)

    assert built.model == llm.DEFAULT_MODEL, "the call happens, on the model the box can run"
    assert len(caplog.records) == 1, "one line per session, not one per turn"
    assert "OPENAI_API_KEY" in caplog.text
    assert os.environ["ANTHROPIC_API_KEY"] not in caplog.text, "names travel, values never do"


def test_a_box_without_the_default_key_says_which_variable_is_missing(
    project: Project, monkeypatch
) -> None:
    """Nothing to fall back to is a clear sentence, not a KeyError three frames down."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    project.llm_model = None
    tc = fake_context("clinica-norte", "reagendamiento")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm.llm_for(tc.tenant, project)


def test_gpt_is_built_with_the_openai_plugin_and_one_cache_key_per_project(
    project: Project, monkeypatch
) -> None:
    """`max_completion_tokens` is the openai name for `max_tokens`; the key pins a shard."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    tc = fake_context("clinica-norte", "reagendamiento")
    project.llm_model = "gpt-5.4-mini"

    built = llm.llm_for(tc.tenant, project)

    assert built.model == "gpt-5.4-mini"
    assert built._opts.max_completion_tokens == llm.MAX_TOKENS
    assert built._opts.prompt_cache_key == "clinica-norte/reagendamiento"
    assert built._opts.reasoning_effort == "none", "a reasoning pass is latency the caller hears"
