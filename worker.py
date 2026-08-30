"""Data plane entry point: one AgentServer, one fleet, every tenant.

`python worker.py console` talks to the agent from the laptop microphone
(`--text` for the keyboard); `python worker.py dev` registers against a
LiveKit server. The VAD is loaded once per process in `prewarm`, inside the
10 s budget, and handed to every job that process runs.
"""

import os

from dotenv import load_dotenv
from livekit.agents import AgentServer, JobContext, JobProcess, cli

from core.providers import vad_for
from core.router import resolve
from core.session import build_session, start_session

load_dotenv()

server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    """Load the VAD before any job arrives; nothing else belongs here (10 s budget)."""
    proc.userdata["vad"] = vad_for()


server.setup_fnc = prewarm


@server.rtc_session(agent_name=os.getenv("FLEET", "cc"))
async def entrypoint(ctx: JobContext) -> None:
    """Resolve the tenant for this job and run its conversation."""
    tc = await resolve(ctx)
    session = build_session(tc, vad=ctx.proc.userdata.get("vad"))
    await start_session(session, tc.project.entry_agent(tc), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
