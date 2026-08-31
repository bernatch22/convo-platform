"""Evals as data: which suites a project declares, how a run is launched, what it scored.

`suites` reads a project's declaration off disk, `runner` spends the money (one
subprocess at a time, killed at fifteen minutes), `runs` is the read side the
console draws, and `filing` is how a run started anywhere else registers itself.
"""

from core.evals import filing, runner, runs, suites

__all__ = ["filing", "runner", "runs", "suites"]
