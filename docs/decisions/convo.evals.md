# `convo.evals`

The reasoning that used to live in the docstrings of `convo/evals/__init__.py`; the code keeps one line per symbol.

## module

`suites` reads a project's declaration off disk, `goldens` reads the cases those
suites run, `runner` spends the money (one subprocess at a time, killed at
fifteen minutes), `runs` is the read side the console draws, and `filing` is how
a run started anywhere else registers itself.
