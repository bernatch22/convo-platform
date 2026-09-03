# `tenants._template.projects.example.evals.metrics`

The reasoning that used to live in the docstrings of `tenants/_template/projects/example/evals/metrics.py`; the code keeps one line per symbol.

## module

What counts as a good reply is a business decision, and so is every threshold:
a clinic's tolerance for tuteo is not a shop's. That is why this file is here
and not in `convo/`.

`tests/evals/` and `convo.testing.reports.report` both build their metrics from this
module, so the CI gate and the HTML a reviewer reads score the same runs by the
same rules.

Every factory returns a FRESH instance: a DeepEval metric keeps the score,
reason and cost of the last case it measured, so sharing one across a
parametrized suite would have the tests overwrite each other's results.

TODO(copy): keep the five below (they are the shape every project in this repo
has), tune the thresholds, and add whatever your business actually cares about.
`docs/evals.md` §7 is the checklist for a new metric.

## consent_policy

`convo sessions eval <id>` scores a stored session of ANY project, so the
name it reads cannot be a business word. Keep this alias.

## line_metric

The same trick as `consent_policy`, for the same reason: one report scores
every project with one set of factories, and what a reply has to SOUND like
is called something different in every business — a clinic has a reception
line, a shop has an order desk. Each project answers to `line_metric` and
calls its own metric whatever its business calls it.
