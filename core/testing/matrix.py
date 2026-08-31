"""The eval matrix: the same goldens, N models, one table that says where they differ.

The LLM is a slot, and a platform that says so has to be able to show it. This
module is the "show it": it reads what DeepEval already produced for each model
— one `EvaluationResult` per model, from the SAME `goldens.json` — and turns it
into a metric × model table plus the list of goldens the models disagreed on.

Nothing here scores anything. Every number is a `MetricData` DeepEval wrote,
which is what keeps the matrix honest: a comparison that re-judged the runs with
a second criterion would be measuring the criterion, not the models.

Two numbers per cell, and both are needed. The **pass rate** is what CI gates
on, and on a suite of eleven goldens it moves in steps of nine points, so a
model that is worse everywhere can tie one that is worse nowhere. The **mean
score** is the continuous half — it separates "0.72 on a 0.7 threshold" from
"0.95" — and it is meaningless on its own, because a metric with a 1.0
threshold (the DAGs) only ever scores 1.0 or 0.0.

The divergences are the point of the exercise. A golden that passes on one model
and fails on the other is a finding to write down, never a golden to soften: the
suite is the fixed thing and the model is the variable, and the moment a golden
is edited so a specific model passes it, the matrix stops comparing anything.

Open source note: the reusable part is the shape — read a run per model, join on
(metric, case), report the cells and the disagreements. Nothing here knows what
a clinic is.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# A case DeepEval could not score at all (a judge error, a crashed run) has no
# number to average, so it is counted as a failure and never as a 0.0 score.
UNSCORED = "unscored"


@dataclass(frozen=True)
class Score:
    """One metric's verdict on one golden, exactly as DeepEval recorded it."""

    metric: str
    case: str
    score: float | None
    passed: bool


@dataclass(frozen=True)
class Cell:
    """What one metric did to the whole suite on one model."""

    metric: str
    model: str
    cases: int
    passed: int
    total_score: float
    scored: int

    @property
    def rate(self) -> float:
        """Share of goldens this metric passed on this model, 0.0 to 1.0."""
        return self.passed / self.cases if self.cases else 0.0

    @property
    def mean(self) -> float | None:
        """Mean score over the goldens that produced one; None when none did."""
        return self.total_score / self.scored if self.scored else None


@dataclass(frozen=True)
class Divergence:
    """One golden that a metric passed on some models and failed on others."""

    metric: str
    case: str
    verdicts: dict[str, bool]

    def summary(self) -> str:
        """`metric — golden: passes on A, fails on B`, the line a card thread quotes."""
        passing = [m for m, ok in self.verdicts.items() if ok]
        failing = [m for m, ok in self.verdicts.items() if not ok]
        return (
            f"{self.metric} — «{self.case}»: passes on {', '.join(passing) or 'nothing'}; "
            f"fails on {', '.join(failing) or 'nothing'}"
        )


@dataclass(frozen=True)
class Matrix:
    """Every metric against every model, plus the goldens they disagreed on."""

    models: list[str]
    metrics: list[str]
    cells: dict[tuple[str, str], Cell]
    divergences: list[Divergence]

    def cell(self, metric: str, model: str) -> Cell | None:
        """The cell at (metric, model), or None when that model never ran that metric."""
        return self.cells.get((metric, model))


def read(result: Any) -> list[Score]:
    """Every (metric, golden) verdict of one DeepEval run, flattened.

    `evaluate()` answers with one `TestResult` per test case, each carrying the
    `MetricData` of every metric that scored it. A case DeepEval could not name
    is keyed by its index, so two runs of the same goldens still line up.
    """
    scores: list[Score] = []
    for index, test in enumerate(getattr(result, "test_results", []) or []):
        case = test.name or f"#{index}"
        for data in test.metrics_data or []:
            scores.append(
                Score(
                    metric=data.name,
                    case=case,
                    score=data.score,
                    passed=bool(data.success) and data.error is None,
                )
            )
    return scores


def build(runs: Mapping[str, Sequence[Score]]) -> Matrix:
    """The matrix for `{model: scores}` — models in the order they were run.

    Metrics are sorted by name so the table reads the same on every run: the
    order `evaluate()` returns them in follows whichever case finished first.
    """
    models = list(runs)
    metrics = sorted({score.metric for scores in runs.values() for score in scores})
    cells = {
        (metric, model): _cell(metric, model, runs[model])
        for metric in metrics
        for model in models
        if any(score.metric == metric for score in runs[model])
    }
    return Matrix(
        models=models, metrics=metrics, cells=cells, divergences=divergences(runs)
    )


def divergences(runs: Mapping[str, Sequence[Score]]) -> list[Divergence]:
    """Every (metric, golden) the models did not agree on, in metric then golden order.

    Only pairs a model actually scored count as disagreement: a golden one run
    never reached is missing evidence, not a difference between two models.
    """
    verdicts: dict[tuple[str, str], dict[str, bool]] = {}
    for model, scores in runs.items():
        for score in scores:
            verdicts.setdefault((score.metric, score.case), {})[model] = score.passed
    return [
        Divergence(metric=metric, case=case, verdicts=seen)
        for (metric, case), seen in sorted(verdicts.items())
        if len(seen) > 1 and len(set(seen.values())) > 1
    ]


def markdown(matrix: Matrix, title: str = "") -> str:
    """The matrix as a Markdown table, ready to paste into a report or a card thread."""
    lines = [f"### {title}"] if title else []
    lines += [
        "| metric | " + " | ".join(matrix.models) + " |",
        "|---|" + "---|" * len(matrix.models),
    ]
    for metric in matrix.metrics:
        cells = [_rendered(matrix.cell(metric, model)) for model in matrix.models]
        lines.append(f"| {metric} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(_divergence_block(matrix))
    return "\n".join(lines)


def _divergence_block(matrix: Matrix) -> str:
    """The findings under the table: what disagreed, or a line saying nothing did."""
    if len(matrix.models) < 2:
        return "_One model: nothing to compare._"
    if not matrix.divergences:
        return "_No divergence: every golden landed the same way on every model._"
    return "\n".join(
        ["**Divergences** (findings, never goldens to soften):"]
        + [f"- {divergence.summary()}" for divergence in matrix.divergences]
    )


def _rendered(cell: Cell | None) -> str:
    """One cell as `passed/cases (rate) · mean score`, or an em dash when it never ran."""
    if cell is None:
        return "—"
    mean = f" · {cell.mean:.2f}" if cell.mean is not None else f" · {UNSCORED}"
    return f"{cell.passed}/{cell.cases} ({cell.rate:.0%}){mean}"


def _cell(metric: str, model: str, scores: Sequence[Score]) -> Cell:
    """Fold one model's verdicts for one metric into the cell that reports them."""
    mine = [score for score in scores if score.metric == metric]
    scored = [score.score for score in mine if score.score is not None]
    return Cell(
        metric=metric,
        model=model,
        cases=len(mine),
        passed=sum(1 for score in mine if score.passed),
        total_score=sum(scored),
        scored=len(scored),
    )
