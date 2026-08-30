"""build_session: assemble the AgentSession for one TenantContext."""

import logging

from livekit.agents import AgentSession, TurnHandlingOptions

from core.context import TenantContext
from core.providers import llm_for, stt_for, tts_for

log = logging.getLogger("platform.session")


def build_session(tc: TenantContext, vad=None) -> AgentSession[TenantContext]:
    """One session per job: providers chosen by the tenant, the context as userdata."""
    return AgentSession[TenantContext](
        llm=llm_for(tc.tenant),
        stt=stt_for(tc.tenant),
        tts=tts_for(tc.tenant, tc.project),
        vad=vad,
        turn_handling=_turn_handling(vad),
        userdata=tc,
        max_tool_steps=4,
    )


async def start_session(session: AgentSession[TenantContext], agent, room=None) -> None:
    """Start the session and, without STT/TTS, switch audio off so text-only projects run anywhere.

    The console starts in audio mode by default; a project without a TTS would
    otherwise fail at the first reply ("tts_node called but no TTS node").
    """
    if room is None:
        await session.start(agent)  # headless (console text mode, tests)
    else:
        await session.start(agent, room=room)
    if session.tts is None:
        session.output.set_audio_enabled(False)
        log.info(
            "no TTS for %s: audio output off (voice arrives in ms-6; use console --text)", agent
        )
    if session.stt is None:
        session.input.set_audio_enabled(False)


def _turn_handling(vad) -> TurnHandlingOptions:
    """Text-only sessions have no audio turns: disable the default (VAD-backed) turn detector."""
    if vad is None:
        return TurnHandlingOptions(turn_detection=None)
    return TurnHandlingOptions()
