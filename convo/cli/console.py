"""`convo console [--tenant T] [--project P] [--text] [--record]`: talk to a project here."""

import argparse
import os

from convo.cli import worker


def main(argv: list[str]) -> int:
    """Pick the tenant and project for this terminal, then hand the rest to the agent runtime."""
    parser = argparse.ArgumentParser(prog="convo console", description=__doc__)
    parser.add_argument("--tenant", help="tenant id (default: DEFAULT_TENANT or clinica-norte)")
    parser.add_argument("--project", help="project id (default: DEFAULT_PROJECT or reagendamiento)")
    known, rest = parser.parse_known_args(argv)
    if known.tenant:
        os.environ["TENANT"] = known.tenant
    if known.project:
        os.environ["PROJECT"] = known.project
    return worker.run(["console", *rest])
