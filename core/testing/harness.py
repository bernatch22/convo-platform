"""Bridge between LiveKit's in-process AgentSession and our tests / DeepEval.

`session.run()` is what the console uses; here it runs headless so a test can
assert on the exact events (messages, tool calls, handoffs) and DeepEval can
score the text. Nothing here touches audio or a LiveKit server.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import date

from livekit.agents import AgentSession
from livekit.agents.metrics import AgentSessionUsage, LLMModelUsage
from livekit.agents.voice.run_result import RunResult

from core.context import TenantContext
from core.registry import load_registry
from core.session import build_session
from core.tools.executor import attach_local_tools

GREETING_WAIT_S = 6.0
TODAY = date(2026, 9, 1)  # a Tuesday: "el jueves" is always two days out in tests


def fake_context(
    tenant_id: str,
    project_id: str,
    channel: str = "chat",
    today: date = TODAY,
) -> TenantContext:
    """A TenantContext for tests: real tenant and project, synthetic ids, a frozen calendar.

    `today` is fixed so a test can name the date it expects ("el jueves" is
    2026-09-03) without the assertion rotting overnight; wired with the tenant's
    adapters and a local executor exactly as `core.router.resolve` wires one.
    """
    tenant = load_registry()[tenant_id]
    project = tenant.projects[project_id]
    tc = TenantContext(
        tenant=tenant,
        project=project,
        channel=channel,
        session_id=f"test-{uuid.uuid4().hex[:8]}",
        git_sha="test",
        project_version="git:test",
        today=today,
    )
    return attach_local_tools(tc)


@dataclass
class Conversation:
    """What a headless run produced: the opening line, one result per input, the token bill."""

    greeting: str
    results: list[RunResult] = field(default_factory=list)
    usage: AgentSessionUsage | None = None

    def reply(self, index: int) -> str:
        """The assistant text of the n-th turn."""
        return text_of(self.results[index])

    def cached_prompt_tokens(self) -> int:
        """Prompt tokens the LLM served from its cache — 0 means the prefix was never reused."""
        if self.usage is None:
            return 0
        return sum(
            model.input_cached_tokens
            for model in self.usage.model_usage
            if isinstance(model, LLMModelUsage)
        )


async def run_conversation(tc: TenantContext, inputs: list[str]) -> Conversation:
    """Start the project's entry agent headless, capture its greeting, run each input as a turn.

    The greeting comes from `on_enter` before any user input, exactly as on a
    real call; goldens that judge the opening line read `Conversation.greeting`.
    """
    session: AgentSession[TenantContext] = build_session(tc)
    async with session:
        await session.start(tc.project.entry_agent(tc))
        await _wait_for_greeting(session)
        conversation = Conversation(greeting=greeting_of(session))
        for text in inputs:
            conversation.results.append(await session.run(user_input=text))
        # read before the context manager closes: leaving it resets the usage collector
        conversation.usage = session.usage
    return conversation


async def run_turns(tc: TenantContext, inputs: list[str]) -> list[RunResult]:
    """Convenience: only the per-input results of `run_conversation`."""
    return (await run_conversation(tc, inputs)).results


def text_of(result: RunResult) -> str:
    """The assistant's spoken text for one turn (RunResult has no .text of its own)."""
    parts = [
        e.item.text_content or ""
        for e in result.events
        if e.type == "message" and e.item.role == "assistant"
    ]
    return " ".join(p.strip() for p in parts if p.strip())


def greeting_of(session: AgentSession) -> str:
    """The first assistant message in the session history."""
    for item in session.history.items:
        if getattr(item, "role", None) == "assistant":
            return item.text_content or ""
    return ""


async def _wait_for_greeting(session: AgentSession, timeout: float = GREETING_WAIT_S) -> None:
    """Poll until the entry agent's greeting lands in the history (or give up quietly)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if greeting_of(session):
            return
        await asyncio.sleep(0.2)
