"""Hybrid prompts: git is the seed, a pinned override replaces the knowledge block; no LLM."""

from pathlib import Path

import pytest

from convo.prompting import stage_prompt
from convo.testing import fake_context

pytestmark = pytest.mark.unit

CLINIC = Path("tenants/clinica-norte/projects/reagendamiento/prompts/knowledge.md").read_text()


def test_the_seed_from_git_opens_every_stage_prompt_by_default() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")

    rendered = stage_prompt(tc, "choose_slot")

    assert rendered.startswith("<clinic_knowledge>\n" + CLINIC)


def test_a_pinned_override_replaces_the_seed_and_nothing_else() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    tc.knowledge_override = "FICHA DE PRUEBA: la consulta cuesta 1 euro."

    rendered = stage_prompt(tc, "identify")

    assert "FICHA DE PRUEBA" in rendered
    assert CLINIC not in rendered
    assert (
        rendered.split("</clinic_knowledge>")[1]
        == stage_prompt(fake_context("clinica-norte", "reagendamiento"), "identify").split(
            "</clinic_knowledge>"
        )[1]
    )
