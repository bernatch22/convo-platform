"""build_session: assemble the AgentSession for one TenantContext."""

from livekit.agents import AgentSession, TurnHandlingOptions

from core.context import TenantContext
from core.providers import llm_for, stt_for, tts_for


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


def _turn_handling(vad) -> TurnHandlingOptions:
    """Text-only sessions have no audio turns: disable the default (VAD-backed) turn detector."""
    if vad is None:
        return TurnHandlingOptions(turn_detection=None)
    return TurnHandlingOptions()
