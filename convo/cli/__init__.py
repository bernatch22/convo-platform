"""The command line: `convo <group> <verb>`, one module per group, no framework."""

from convo.cli import routes, sessions, versions

GROUPS = {"sessions": sessions.main, "routes": routes.main, "versions": versions.main}
USAGE = "usage: python -m convo sessions|routes|versions ..."


def main(argv: list[str]) -> int:
    """Route the first word to its group; print usage on anything unknown."""
    if not argv or argv[0] not in GROUPS:
        print(USAGE)
        return 2
    return GROUPS[argv[0]](argv[1:])
