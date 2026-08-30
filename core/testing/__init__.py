"""Test harness: run conversations in-process (no room, no audio) for unit tests and evals."""

from core.testing.harness import fake_context, run_turns, text_of

__all__ = ["fake_context", "run_turns", "text_of"]
