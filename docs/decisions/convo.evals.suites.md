# `convo.evals.suites`

The reasoning that used to live in the docstrings of `convo/evals/suites.py`; the code keeps one line per symbol.

## module

A project declares its suites in `tenants/<id>/projects/<id>/evals/suites.json`:

    {"ring1": "tests/evals/test_reception_deepeval.py"}

The key is free text on purpose. Ring 1 today, personas tomorrow: a new suite is
one line of a customer's own data, never a branch in `core`. The file is read,
never imported, so this module keeps the rule the whole runtime keeps — `core`
does not know any tenant exists.
