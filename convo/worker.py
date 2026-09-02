"""Data plane entry point: one AgentServer, one fleet, every tenant.

Decisions: docs/decisions/convo.worker.md
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import AgentServer, JobContext, JobProcess, cli
from livekit.agents.cli import AgentsConsole

from convo import settings
from convo.domain.context import TenantContext
from convo.providers import vad_for
from convo.session import recordings
from convo.session.build import build_session, start_session
from convo.session.router import resolve
from convo.state.attach import close_log
from convo.state.log import record as record_event
from convo.supervision.control import SupervisorControl
from convo.supervision.monitor import watch_supervisors

load_dotenv()

log = logging.getLogger("platform.worker")
server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    """Load the VAD before any job arrives; nothing else belongs here (10 s budget)."""
    proc.userdata["vad"] = vad_for()


server.setup_fnc = prewarm


@server.rtc_session(agent_name=settings.fleet())
async def entrypoint(ctx: JobContext) -> None:
    """Resolve the tenant for this job and run its conversation."""
    tc = await resolve(ctx)
    audio = audio_destination(ctx, tc)
    session = build_session(tc, vad=ctx.proc.userdata.get("vad"))
    # A supervisor's verbs are aimed at THIS session, so the control is built with
    # it and hung on the context every stage already carries. The watch stays out
    # of `build_session` because it is about the ROOM: a console run has no room,
    # gets no control, and so has no second human to obey. The room is passed too
    # because `transfer` needs a NAME and a caller identity, and only the room has
    # those — a console run is refused the verb rather than guessing at them.
    tc.supervisor = SupervisorControl(tc, session, ctx.room)
    watch_supervisors(ctx.room, tc, tc.supervisor)
    ctx.add_shutdown_callback(_report_filer(ctx, session, tc))
    await start_session(
        session,
        tc.project.entry_agent(tc),
        room=ctx.room,
        record=audio is not None,
        channel=tc.channel,
    )
    if audio is not None:
        # Written the moment the recorder is up, not at the end: the pointer has
        # to survive the SIGKILL the audio itself now survives, and its `t_ms`
        # is what `core.testing.audio` reads as sample 0 of the OGG.
        record_event(tc, "audio.start", {"path": str(audio)})


def audio_destination(ctx: JobContext, tc: TenantContext) -> Path | None:
    """Where this call's OGG will be written, or None when it keeps no audio."""
    if tc.channel != "voice" or os.getenv("RECORD") == "0":
        return None
    if not recordings.keep(tc.project):
        return None
    console = AgentsConsole.get_instance()
    if console.enabled:
        return Path(console.session_directory) / recordings.FILENAME if console.record else None
    return recordings.aim(ctx, tc.session_id)


def _report_filer(ctx: JobContext, session, tc):
    """A shutdown callback that files the framework's end-of-call report on the session row."""

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
