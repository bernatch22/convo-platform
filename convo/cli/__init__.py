"""The command line: `convo <group> <verb>`, one module per group, argparse and nothing else."""

from convo.cli import api, console, evals, routes, sessions, versions, worker

GROUPS = {
    "console": console.main,
    "worker": worker.main,
    "api": api.main,
    "sessions": sessions.main,
    "routes": routes.main,
    "versions": versions.main,
    "evals": evals.main,
}
USAGE = """usage: convo <group> [args]

  console   talk to a project from this terminal (--text for the keyboard, --record for OGG)
  worker    run the fleet against a LiveKit server (dev | start)
  api       run the control plane and the console UI
  sessions  list | show <id> | tail [<id>] | eval <id> [--voice] | score <id> [--free]
  routes    list | seed | add <fleet> <number> <tenant> <project> [voice|chat]
  versions  list | pin <tenant> <project> <version> [<file>]: the knowledge override
  evals     report <t> <p> [--model M] | nightly [--dry-run …] | record [<t> <p>] | golden
"""


def main(argv: list[str]) -> int:
    """Route the first word to its group; print usage on anything unknown."""
    if not argv or argv[0] not in GROUPS:
        print(USAGE)
        return 2
    return GROUPS[argv[0]](argv[1:])


def main_argv() -> int:
    """The `convo` console script: `main` over the process arguments."""
    import sys

    return main(sys.argv[1:])
