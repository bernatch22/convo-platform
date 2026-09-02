"""`convo worker dev|start [livekit flags]`: run the fleet against a LiveKit server."""

import sys

USAGE = "usage: convo worker dev | start | console [flags the agent runtime understands]"


def main(argv: list[str]) -> int:
    """Refuse an unknown verb here, where the message is ours; the runtime parses the rest."""
    if not argv or argv[0] not in ("dev", "start", "console", "download-files"):
        print(USAGE)
        return 2
    return run(argv)


def run(argv: list[str]) -> int:
    """Start the agent runtime with these arguments, exactly as `python -m convo.worker` would."""
    from livekit.agents import cli

    from convo.worker import server

    sys.argv = ["convo worker", *argv]
    cli.run_app(server)
    return 0
