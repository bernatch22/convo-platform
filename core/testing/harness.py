"""Bridge between LiveKit's in-process AgentSession and our tests / DeepEval.

`session.run()` is what the console uses; here it runs headless so a test can
assert on the exact events (messages, tool calls, handoffs) and DeepEval can
score the text. Nothing here touches audio or a LiveKit server.
"""

import asyncio
import uuid

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


async def run_turns(tc: TenantContext, inputs: list[str]) -> list[RunResult]:
    """Start the project's entry agent headless and run each user input as one turn.

    The greeting produced by `on_enter` is awaited before the first input so the
    history looks like a real call. Returns one RunResult per input.
    """
    session: AgentSession[TenantContext] = build_session(tc)
    results: list[RunResult] = []
    async with session:
        await session.start(tc.project.entry_agent(tc))
        await _wait_for_greeting(session)
        for text in inputs:
            results.append(await session.run(user_input=text))
    return results


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
