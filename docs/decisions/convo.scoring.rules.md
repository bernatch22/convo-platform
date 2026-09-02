# `convo.scoring.rules`

The reasoning that used to live in the docstrings of `convo/scoring/rules.py`; the code keeps one line per symbol.

## module

A post-call score asks four questions of code and one of a judge, and three of
the five need words only the business owns: the register it speaks in, the
nouns that belong to the shop next door, and what "a good call" means here.
That is what this dataclass carries, and a project declares it in
`tenants/<id>/projects/<p>/evals/scoring.py` next to its goldens.

Loaded the way `core.registry` loads a tenant — by name, at call time, inside a
try/except — so a project with no rules file is scored on what the platform can
decide alone instead of taking the scorer down, and `core/` still compiles with
no customer folder on disk.

Deliberately free of `deepeval`: this module is imported by the projects
themselves and by the deterministic path, which must not pay for a judge stack
to find out that a call said "te" to a patient.

## ScoringRules

Every field is optional and an empty one disables its check rather than
failing it: a project that declares no forbidden register is reported as
"not applicable", never as "passed", because the two are different facts
and only one of them is worth acting on.

## rules_for

A missing file, a broken import or an attribute of the wrong type all mean
the same thing to the scorer — this project told us nothing — and all of
them are logged once and survived. A tenant whose eval package does not
import must not stop the platform scoring everybody else's calls.
