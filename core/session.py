"""build_session: assemble the AgentSession for one TenantContext.

Two shapes of session leave this module. With STT and TTS (keys present) the
session listens and speaks: Soniox endpointing and the local turn detector
share the decision of when the caller has finished, a real interruption needs
two words so a "vale" does not cut the agent off, and every spoken word comes
back with its time for the log. Without them it is text only, and audio is
switched off so the console's default audio mode does not crash.
"""

import logging

from livekit.agents import AgentSession, TurnHandlingOptions
from livekit.agents.voice.turn import EndpointingOptions, InterruptionOptions

from core.context import TenantContext
from core.observability.observers import observe
from core.providers import llm_for, stt_for, tts_for, turn_detector_for

log = logging.getLogger("platform.session")

ENDPOINT_MIN_DELAY_S = 0.3
ENDPOINT_MAX_DELAY_S = 2.5
INTERRUPTION_MIN_WORDS = 2
PREEMPTIVE_MAX_RETRIES = 1


def build_session(tc: TenantContext, vad=None) -> AgentSession[TenantContext]:
    """One session per job: providers chosen by the tenant, the context as userdata.

    The observers are wired here and nowhere else. They have to be subscribed
    before the session starts — the entry agent's `on_enter` runs inside
    `session.start`, so a handler attached afterwards misses the greeting that
    opened the call — and building the session is the one moment every caller
    (worker, console, harness) passes through.
    """
    stt = stt_for(tc.tenant, tc.project)
    tts = tts_for(tc.tenant, tc.project)
    voice = stt is not None and tts is not None and vad is not None
    session = AgentSession[TenantContext](
        llm=llm_for(tc.tenant),
        stt=stt,
        tts=tts,
        vad=vad,
        turn_handling=voice_turn_handling() if voice else text_turn_handling(),
        use_tts_aligned_transcript=True if voice else None,
        userdata=tc,
        max_tool_steps=4,
    )
    observe(session, tc)
    return session


def voice_turn_handling() -> TurnHandlingOptions:
    """Semantic end of turn, short endpointing window, two-word interruptions, one retry."""
    return TurnHandlingOptions(
        turn_detection=turn_detector_for(),
        endpointing=EndpointingOptions(
            min_delay=ENDPOINT_MIN_DELAY_S, max_delay=ENDPOINT_MAX_DELAY_S
        ),
        interruption=InterruptionOptions(
            min_words=INTERRUPTION_MIN_WORDS, resume_false_interruption=True
        ),
        preemptive_generation={"max_retries": PREEMPTIVE_MAX_RETRIES},
    )


def text_turn_handling() -> TurnHandlingOptions:
    """Text-only sessions have no audio turns: disable the default (VAD-backed) turn detector."""
    return TurnHandlingOptions(turn_detection=None)


async def start_session(session: AgentSession[TenantContext], agent, room=None) -> None:
    """Start the session; without STT/TTS switch audio off so text-only projects run anywhere."""
    if room is None:
        await session.start(agent)  # headless (console text mode, tests)
    else:
        await session.start(agent, room=room)
    if session.tts is None:
        session.output.set_audio_enabled(False)
        log.info(
            "no TTS for %s: audio output off (set ELEVENLABS_API_KEY, or console --text)", agent
        )
    if session.stt is None:
        session.input.set_audio_enabled(False)
