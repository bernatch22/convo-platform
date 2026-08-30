"""Data plane entry point: one AgentServer, one fleet, every tenant.

`python worker.py console --text` talks to the agent from the terminal;
`python worker.py dev` registers against a LiveKit server.
"""

import os

from dotenv import load_dotenv
from livekit.agents import AgentServer, JobContext, cli

from core.router import resolve
from core.session import build_session, start_session

load_dotenv()

server = AgentServer()


@server.rtc_session(agent_name=os.getenv("FLEET", "cc"))
async def entrypoint(ctx: JobContext) -> None:
    """Resolve the tenant for this job and run its conversation."""
    tc = await resolve(ctx)
    session = build_session(tc)
    await start_session(session, tc.project.entry_agent(tc), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
