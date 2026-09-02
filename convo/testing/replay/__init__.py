"""Ring 3: a stored session read back as the same ConversationalTestCase ring 1 scores.

Decisions: docs/decisions/convo.testing.replay.md
"""

from collections.abc import Mapping

from deepeval.test_case import ConversationalTestCase

from convo.state.store import Store
from convo.testing.harness import fake_context
from convo.testing.metrics.deepeval import tool_descriptions
from convo.testing.replay.tools import NO_PAYLOAD, missing_tool_outputs
from convo.testing.replay.turns import turns_from

__all__ = [
    "NO_PAYLOAD",
    "conversational_case_from",
    "descriptions_for",
    "missing_tool_outputs",
    "turns_from",
]

SCENARIO = "A real {channel} session of {tenant}/{project}, replayed from its append-only log."


def conversational_case_from(
    store: Store,
    session_id: str,
    descriptions: Mapping[str, str] | None = None,
) -> ConversationalTestCase:
    """One stored session as the multi-turn case a ConversationalDAGMetric reads."""
    row = store.session(session_id)
    if row is None:
        raise LookupError(f"no session {session_id!r} in this store")
    return ConversationalTestCase(
        turns=turns_from(store.events(session_id), descriptions),
        name=session_id,
        scenario=SCENARIO.format(channel=row.channel, tenant=row.tenant, project=row.project),
    )


def descriptions_for(tenant_id: str, project_id: str) -> dict[str, str]:
    """Every tool of every stage of a project, described as the model reads it."""
    return tool_descriptions(fake_context(tenant_id, project_id))
