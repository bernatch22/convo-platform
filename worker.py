"""Data plane entry point: one AgentServer, one fleet, every tenant.

`python worker.py console` talks to the agent from the laptop microphone
(`--text` for the keyboard); `python worker.py dev` registers against a
LiveKit server. The VAD is loaded once per process in `prewarm`, inside the
10 s budget, and handed to every job that process runs.
"""

import logging
import os

from dotenv import load_dotenv
from livekit.agents import AgentServer, JobContext, JobProcess, cli

from core.providers import vad_for
from core.router import resolve
from core.session import build_session, start_session
from core.state.attach import close_log

load_dotenv()

log = logging.getLogger("platform.worker")
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
    ctx.add_shutdown_callback(_report_filer(ctx, session, tc))
    await start_session(session, tc.project.entry_agent(tc), room=ctx.room)


def _report_filer(ctx: JobContext, session, tc):
    """A shutdown callback that files the framework's end-of-call report on the session row.

    It must never raise: a report that cannot be built is a warning in the
    worker's log, not a job that dies on the way out and loses the outcome too.
    """

    async def persist() -> None:
        try:
            report = ctx.make_session_report(session).to_dict()
        except Exception:
            log.exception("session report unavailable for %s", tc.label())
            report = None
        close_log(tc, report)

    return persist


if __name__ == "__main__":
    cli.run_app(server)
