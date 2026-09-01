"""Evals as data: which suites a project declares, how a run is launched, what it scored.

`suites` reads a project's declaration off disk, `goldens` reads the cases those
suites run, `runner` spends the money (one subprocess at a time, killed at
fifteen minutes), `runs` is the read side the console draws, and `filing` is how
a run started anywhere else registers itself.
"""

from core.evals import filing, goldens, runner, runs, suites

__all__ = ["filing", "goldens", "runner", "runs", "suites"]
