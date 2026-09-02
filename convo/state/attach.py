"""Opening and closing a session's log: the two ends of `core.state`, in one file.

Decisions: docs/decisions/convo.state.attach.md
"""

import time
from typing import Any

from convo.domain.context import TenantContext
from convo.session import pipeline
from convo.state.log import EventLog
from convo.state.store import SessionRow, Store


def attach_log(tc: TenantContext, store: Store, sip: dict[str, str] | None = None) -> TenantContext:
    """Open the session in the store, hang an EventLog on the context, write `session.start`."""
    store.open_session(
        SessionRow(
            id=tc.session_id,
            tenant=tc.tenant.id,
            project=tc.project.id,
            channel=tc.channel,
            started_at=time.time(),
        )
    )
    tc.log = EventLog(tc.session_id, store)
    tc.log.append(
        "session.start",
        {
            "tenant": tc.tenant.id,
            "project": tc.project.id,
            "channel": tc.channel,
            "git_sha": tc.git_sha,
            "project_version": tc.project_version,
            "pipeline": pipeline.running(tc.project, tc.channel),
            **({"sip": dict(sip)} if sip else {}),
        },
    )
    return tc


def close_log(tc: TenantContext, report: dict[str, Any] | None = None) -> None:
    """Close the session row with the outcome its log recorded, and file the report."""
    if tc.log is None:
        return
    tc.log.store.close_session(tc.session_id, outcome_of(tc), report)


def outcome_of(tc: TenantContext) -> str:
    """The outcome the observers wrote on `session.end`, or `dropped` if it never came."""
    for event in reversed(tc.log.events() if tc.log else []):
        if event.kind == "session.end":
            return str(event.payload.get("outcome", "completed"))
    return "dropped"
