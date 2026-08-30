"""attach_log: give a TenantContext its session log and register the session with the store."""

import time

from core.context import TenantContext
from core.state.log import EventLog
from core.state.store import SessionRow, Store


def attach_log(tc: TenantContext, store: Store) -> TenantContext:
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
        },
    )
    return tc
