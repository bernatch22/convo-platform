"""Test harness: run conversations in-process (no room, no audio) for unit tests and evals."""

from core.testing.harness import (
    MODEL_ENV,
    TODAY,
    Conversation,
    Exchange,
    LiveCall,
    PlatformCall,
    fake_context,
    final_message,
    live_conversation,
    model_under_test,
    run_conversation,
    run_turns,
    text_of,
)

__all__ = [
    "MODEL_ENV",
    "TODAY",
    "Conversation",
    "Exchange",
    "LiveCall",
    "PlatformCall",
    "fake_context",
    "final_message",
    "live_conversation",
    "model_under_test",
    "run_conversation",
    "run_turns",
    "text_of",
]
