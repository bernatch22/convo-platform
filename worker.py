"""Data plane entry point: one AgentServer, one fleet, every tenant.

Run `python worker.py console --text` to talk to the agent from the terminal,
`python worker.py dev` against a LiveKit server. The entrypoint is wired here
and filled in by later milestones (ms-1 adds the first session).
"""

import os

from livekit.agents import AgentServer, JobContext, cli

server = AgentServer()


@server.rtc_session(agent_name=os.getenv("FLEET", "cc"))
async def entrypoint(ctx: JobContext) -> None:
    """Resolve the tenant for this job and start its session (implemented in ms-1)."""
    raise NotImplementedError(
        "ms-0 ships the skeleton only. ms-1 resolves the tenant and starts an AgentSession."
    )


if __name__ == "__main__":
    cli.run_app(server)
