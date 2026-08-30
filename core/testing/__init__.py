"""Test harness: run conversations in-process (no room, no audio) for unit tests and evals."""

from core.testing.harness import Conversation, fake_context, run_conversation, run_turns, text_of

__all__ = ["Conversation", "fake_context", "run_conversation", "run_turns", "text_of"]
