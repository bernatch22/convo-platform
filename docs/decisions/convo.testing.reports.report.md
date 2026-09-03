# `convo.testing.reports.report`

The reasoning that used to live in the docstrings of `convo/testing/reports/report.py`; the code keeps one line per symbol.

## module

`deepeval test run` is the CI gate (pass/fail); this module is the reviewer's
view: it runs the same goldens through the same cases and the same metrics and
writes a self-contained HTML under tmp/reports/deepeval/. Usage:

    uv run python -m convo.testing.reports.report clinica-norte reagendamiento
    uv run python -m convo.testing.reports.report tienda-sur pedidos --model claude-haiku-4-5 \
        --model gpt-5.4-mini

The metrics are the project's own (`evals/metrics.py`), never a copy kept here:
a criterion that drifts between the gate and the report is worse than no report,
because it shows a reviewer a score CI never computed. ArgumentCorrectness is
the one metric the suite runs and this does not — `evaluate()` scores every case
with every metric, and a judge asked about the arguments of a turn that called
nothing has nothing to read. It stays in the pytest suite, where it is applied
only to the goldens that call.

Two `evaluate()` calls per model, because DeepEval will not mix the two case
types in one run: the turn-level metrics read one input and the turn that
answered it, the conversational ones read the whole call including the opening
line and the platform's own writes. Both come out of the SAME conversations —
the model turn is what costs money, and running the goldens twice to score them
twice would double the bill for identical evidence.

Given more than one `--model`, every model answers the same `goldens.json`,
untouched, and the run ends on the metric × model table (`convo.testing.reports.matrix`).
A golden that only passes on one model is a finding for the report, never a
golden to rewrite until both models pass it: soften it and the matrix stops
comparing anything.

At the end the run files itself with the control plane (`POST /evals/runs`), so
a report written on a laptop shows up on the console's evals screen next to the
runs the box launched itself. A control plane that is not answering costs
nothing: the HTML on disk is still the evidence.

## suite_name

No slash anywhere in it, however much it wants to read like a path: DeepEval
pastes the identifier straight into the HTML filename, so the first one
turns the run into a write to a directory nobody created and the whole
report dies on a `FileNotFoundError` after every golden has been paid for.
