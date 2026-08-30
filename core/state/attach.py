"""Opening and closing a session's log: the two ends of `core.state`, in one file.

`attach_log` runs when the job starts, `close_log` when it shuts down. Between
them the log is written by the observers and the executor, append by append,
so closing adds no events — only the framework's end-of-call report, which is
the one artefact that does not exist until the call is over.
"""

import time
from typing import Any

from core.context import TenantContext
from core.state.log import EventLog
from core.state.store import SessionRow, Store


def attach_log(tc: TenantContext, store: Store, sip: dict[str, str] | None = None) -> TenantContext:
    """Open the session in the store, hang an EventLog on the context, write `session.start`.

    `sip` is the caller's `sip.*` attributes when the session came in over the
    phone: the dialled number, the carrier's call id and the headers the trunk
    was told to keep. They belong on the very first event — an audit asks which
    number was dialled long before it asks what was said.
    """
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
            **({"sip": dict(sip)} if sip else {}),
        },
    )
    return tc


def close_log(tc: TenantContext, report: dict[str, Any] | None = None) -> None:
    """Close the session row with the outcome its log recorded, and file the report.

    The events are already durable — every append reached the store during the
    call — so this only writes what exists at the end. A context with no log
    has nothing to close.
    """
    if tc.log is None:
        return
    tc.log.store.close_session(tc.session_id, outcome_of(tc), report)


def outcome_of(tc: TenantContext) -> str:
    """The outcome the observers wrote on `session.end`, or `dropped` if it never came.

    A process killed mid-call leaves no close event, and `dropped` is exactly
    what that means: the log ends where the call did.
    """
    for event in reversed(tc.log.events() if tc.log else []):
        if event.kind == "session.end":
            return str(event.payload.get("outcome", "completed"))
    return "dropped"
