"""Providers: the only package that knows which vendor backs each capability.

One module per capability — `llm`, `stt`, `tts`, `turn` — each exposing a
single factory that reads the project's data and the environment and returns
a configured plugin, or None when the key for it is absent so a text-only
session keeps working on a laptop with nothing but an Anthropic key.

Open source note: swapping a vendor is one file here; nothing in `core/session`
or in a tenant names a plugin.
"""

from core.providers.llm import llm_for
from core.providers.stt import stt_for
from core.providers.tts import tts_for
from core.providers.turn import turn_detector_for, vad_for

__all__ = ["llm_for", "stt_for", "tts_for", "turn_detector_for", "vad_for"]
