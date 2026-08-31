"""The eval matrix: one goldens.json, two models, and a table that says where they differ.

Nothing here calls a model or a judge. What is asserted is the wiring — that
choosing a model travels as project data down the same road a real call takes,
that choosing a wrong one is refused instead of silently measured, and that the
table and its divergences are read off DeepEval's own verdicts.
"""

import dataclasses

import pytest

from core.providers import llm
from core.registry import load_registry
from core.testing import fake_context, matrix, model_under_test
from core.testing.harness import MODEL_ENV

pytestmark = pytest.mark.unit


# --- choosing the model under test -------------------------------------------


def test_with_nothing_chosen_the_project_keeps_its_own_model(monkeypatch) -> None:
    monkeypatch.delenv(MODEL_ENV, raising=False)

    assert model_under_test() is None
    assert fake_context("clinica-norte", "reagendamiento").project.llm_model is None


def test_the_environment_moves_every_golden_onto_the_other_model(monkeypatch) -> None:
    monkeypatch.setenv(MODEL_ENV, llm.GPT_MINI)

    assert model_under_test() == llm.GPT_MINI
    assert fake_context("tienda-sur", "pedidos").project.llm_model == llm.GPT_MINI


def test_an_explicit_model_wins_over_the_environment(monkeypatch) -> None:
    monkeypatch.setenv(MODEL_ENV, llm.GPT_MINI)

    assert model_under_test(llm.HAIKU) == llm.HAIKU


def test_a_model_the_platform_will_not_run_is_refused_not_quietly_replaced() -> None:
    with pytest.raises(ValueError, match="gpt-4o"):
        model_under_test("gpt-4o")


def test_choosing_a_model_never_moves_the_registrys_own_project(monkeypatch) -> None:
    monkeypatch.delenv(MODEL_ENV, raising=False)
    fake_context("clinica-norte", "reagendamiento", llm_model=llm.GPT_MINI)

    assert load_registry()["clinica-norte"].projects["reagendamiento"].llm_model is None


# --- the provider slot -------------------------------------------------------


def test_the_model_a_project_names_decides_which_vendor_answers(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    tc = fake_context("clinica-norte", "reagendamiento")
    gpt = dataclasses.replace(tc.project, llm_model=llm.GPT_MINI)

    assert llm.family(llm.llm_model(tc.project)) == "anthropic"
    assert llm.family(llm.llm_model(gpt)) == "openai"
    assert llm.llm_for(tc.tenant, gpt).model == llm.GPT_MINI


def test_a_project_naming_a_model_nobody_priced_falls_back_on_the_phone() -> None:
    tc = fake_context("clinica-norte", "reagendamiento")
    unpriced = dataclasses.replace(tc.project, llm_model="gpt-4o")

    assert llm.llm_model(unpriced) == llm.DEFAULT_MODEL


# --- the table ---------------------------------------------------------------


def scores(model_verdicts: dict[str, bool], metric: str = "Reception line") -> list[matrix.Score]:
    """One metric's verdicts over a handful of goldens, as DeepEval would have recorded them."""
    return [
        matrix.Score(metric=metric, case=case, score=1.0 if ok else 0.0, passed=ok)
        for case, ok in model_verdicts.items()
    ]


def test_a_cell_reports_the_pass_rate_and_the_mean_of_one_metric_on_one_model() -> None:
    built = matrix.build({"haiku": scores({"a": True, "b": True, "c": False})})

    cell = built.cell("Reception line", "haiku")
    assert cell is not None
    assert (cell.passed, cell.cases) == (2, 3)
    assert cell.rate == pytest.approx(2 / 3)
    assert cell.mean == pytest.approx(2 / 3)


def test_a_golden_that_passes_on_one_model_and_fails_on_the_other_is_a_divergence() -> None:
    built = matrix.build(
        {
            "haiku": scores({"a": True, "b": True}),
            "gpt": scores({"a": True, "b": False}),
        }
    )

    assert [d.case for d in built.divergences] == ["b"]
    assert built.divergences[0].verdicts == {"haiku": True, "gpt": False}


def test_a_golden_only_one_model_ever_reached_is_missing_evidence_not_a_difference() -> None:
    built = matrix.build({"haiku": scores({"a": True, "b": False}), "gpt": scores({"a": True})})

    assert built.divergences == []


def test_the_table_names_every_model_and_says_when_nothing_diverged() -> None:
    built = matrix.build({"haiku": scores({"a": True}), "gpt": scores({"a": True})})

    table = matrix.markdown(built, title="clinica-norte/reagendamiento")

    assert "| metric | haiku | gpt |" in table
    assert "1/1 (100%)" in table
    assert "No divergence" in table


def test_a_metric_one_model_never_ran_shows_as_a_gap_and_not_as_a_zero() -> None:
    built = matrix.build(
        {"haiku": scores({"a": True}, metric="Grounded facts"), "gpt": scores({"a": True})}
    )

    assert built.cell("Grounded facts", "gpt") is None
    assert "—" in matrix.markdown(built)


def test_a_case_deepeval_could_not_score_counts_as_a_failure_and_never_as_a_zero() -> None:
    unscored = [matrix.Score(metric="Reception line", case="a", score=None, passed=False)]
    built = matrix.build({"haiku": unscored})

    cell = built.cell("Reception line", "haiku")
    assert cell is not None and cell.mean is None
    assert matrix.UNSCORED in matrix.markdown(built)
