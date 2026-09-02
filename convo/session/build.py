"""build_session: assemble the AgentSession for one TenantContext.

Decisions: docs/decisions/convo.session.build.md
"""

import logging

from livekit.agents import AgentSession, TurnHandlingOptions
from livekit.agents.voice.room_io import RoomOptions
from livekit.agents.voice.turn import EndpointingOptions, InterruptionOptions

from convo.domain.context import TenantContext
from convo.domain.contracts import Channel
from convo.observability.observers import observe
from convo.observability.voice import observe_voice
from convo.providers import llm_for, stt_for, tts_for, turn_detector_for

log = logging.getLogger("platform.session")

ENDPOINT_MIN_DELAY_S = 0.3
ENDPOINT_MAX_DELAY_S = 2.5
INTERRUPTION_MIN_WORDS = 2


def build_session(tc: TenantContext, vad=None) -> AgentSession[TenantContext]:
    """One session per job: providers chosen by the tenant, the context as userdata."""
    audible = tc.channel == "voice"
    stt = stt_for(tc.tenant, tc.project) if audible else None
    tts = tts_for(tc.tenant, tc.project) if audible else None
    vad = vad if audible else None
    voice = stt is not None and tts is not None and vad is not None
    session = AgentSession[TenantContext](
        llm=llm_for(tc.tenant, tc.project),
        stt=stt,
        tts=tts,
        vad=vad,
        turn_handling=voice_turn_handling() if voice else text_turn_handling(),
        use_tts_aligned_transcript=True if voice else None,
        userdata=tc,
        max_tool_steps=4,
    )
    observe(session, tc)
    if voice:
        observe_voice(session, tc)
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
        # OFF by the human's decision (2026-08-31, call AJ_rt86KogpPxDa): with
        # Soniox closing a turn in ~0.33s there is no window for speculation to
        # hide Haiku's ttft — it appeared whole in the gap regardless — so the
        # extra cache-read calls bought nothing. Generation starts only when the
        # end of turn is confirmed.
        preemptive_generation={"enabled": False},
    )


def text_turn_handling() -> TurnHandlingOptions:
    """Text-only sessions have no audio turns: disable the default (VAD-backed) turn detector."""
    return TurnHandlingOptions(turn_detection=None)


def channel_options(channel: Channel) -> RoomOptions:
    """How the session meets the room: chat is text both ways, voice keeps its tracks."""
    if channel == "chat":
        return RoomOptions(audio_input=False, audio_output=False)
    return RoomOptions()


async def start_session(
    session: AgentSession[TenantContext],
    agent,
    room=None,
    record: bool = False,
    channel: Channel = "voice",
) -> None:
    """Start the session; without STT/TTS switch audio off so text-only projects run anywhere."""
    if room is None:
        await session.start(agent, record=record)  # headless (console, tests)
    else:
        await session.start(agent, room=room, room_options=channel_options(channel), record=record)
    if session.tts is None:
        session.output.set_audio_enabled(False)
        log.info(
            "no TTS for %s: audio output off (set ELEVENLABS_API_KEY, or console --text)", agent
        )
    if session.stt is None:
        session.input.set_audio_enabled(False)
