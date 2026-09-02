"""Providers: the only package that knows which vendor backs each capability.

Decisions: docs/decisions/convo.providers.md
"""

from convo.providers.llm import llm_for
from convo.providers.stt import stt_for
from convo.providers.tts import tts_for
from convo.providers.turn import turn_detector_for, vad_for

__all__ = ["llm_for", "stt_for", "tts_for", "turn_detector_for", "vad_for"]
