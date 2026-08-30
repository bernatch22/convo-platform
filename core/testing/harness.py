"""Bridge between LiveKit's in-process AgentSession and our tests / DeepEval.

`session.run()` is what the console uses; here it runs headless so a test can
assert on the exact events (messages, tool calls, handoffs) and DeepEval can
score the text. Nothing here touches audio or a LiveKit server.
"""

import asyncio
import uuid
from dataclasses import dataclass, field

from livekit.agents import AgentSession
from livekit.agents.voice.run_result import RunResult

from core.context import TenantContext
from core.registry import load_registry
from core.session import build_session

GREETING_WAIT_S = 6.0


def fake_context(tenant_id: str, project_id: str, channel: str = "chat") -> TenantContext:
    """A TenantContext for tests: real tenant and project, synthetic session ids."""
    tenant = load_registry()[tenant_id]
    project = tenant.projects[project_id]
    return TenantContext(
        tenant=tenant,
        project=project,
        channel=channel,
        session_id=f"test-{uuid.uuid4().hex[:8]}",
        git_sha="test",
        project_version="git:test",
    )


@dataclass
class Conversation:
    """What a headless run produced: the agent's opening line and one result per input."""

    greeting: str
    results: list[RunResult] = field(default_factory=list)

    def reply(self, index: int) -> str:
        """The assistant text of the n-th turn."""
        return text_of(self.results[index])


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
