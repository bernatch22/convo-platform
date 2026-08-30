"""Hybrid prompts: git is the seed, a pinned override replaces the knowledge block; no LLM."""

import importlib

import pytest

from core.testing import fake_context

pytestmark = pytest.mark.unit

prompts = importlib.import_module("tenants.clinica-norte.projects.reagendamiento.prompts")
knowledge = importlib.import_module("tenants.clinica-norte.projects.reagendamiento.knowledge")


def test_the_seed_from_git_opens_every_stage_prompt_by_default() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")

    rendered = prompts.choose_slot_prompt(tc)

    assert rendered.startswith("<clinic_knowledge>\n" + knowledge.CLINIC)


def test_a_pinned_override_replaces_the_seed_and_nothing_else() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    tc.knowledge_override = "FICHA DE PRUEBA: la consulta cuesta 1 euro."

    rendered = prompts.identify_prompt(tc)

    assert "FICHA DE PRUEBA" in rendered
    assert knowledge.CLINIC not in rendered
    assert (
        rendered.split("</clinic_knowledge>")[1]
        == prompts.identify_prompt(fake_context("clinica-norte", "reagendamiento")).split(
            "</clinic_knowledge>"
        )[1]
    )
