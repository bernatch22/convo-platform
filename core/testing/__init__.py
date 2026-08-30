"""Test harness: run conversations in-process (no room, no audio) for unit tests and evals."""

from core.testing.harness import (
    TODAY,
    Conversation,
    fake_context,
    final_message,
    run_conversation,
    run_turns,
    text_of,
)

__all__ = [
    "TODAY",
    "Conversation",
    "fake_context",
    "final_message",
    "run_conversation",
    "run_turns",
    "text_of",
]
