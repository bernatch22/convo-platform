"""`convo sessions`: list recorded sessions, or show one as its seq table."""

import json
import time
from typing import Any

from core.state.events import Event
from core.state.store import SQLiteStore, Store

LIST_HEADER = (
    f"{'id':<26} {'tenant/project':<32} {'channel':<7} {'started':<16} {'outcome':<10} events"
)
SHOW_HEADER = f"{'seq':>4} {'t_ms':>7}  {'kind':<18} payload"
METRIC_KEYS = ("llm_node_ttft", "e2e_latency", "transcription_delay", "end_of_turn_delay")


def main(argv: list[str], store: Store | None = None) -> int:
    """`list` prints every session newest first; `show <id>` prints one session's events."""
    store = store or SQLiteStore()
    if argv[:1] == ["list"]:
        return list_sessions(store)
    if argv[:1] == ["show"] and len(argv) == 2:
        return show_session(store, argv[1])
    print("usage: python -m convo sessions list | show <id>")
    return 2


def list_sessions(store: Store) -> int:
    """One line per session: id, tenant/project, channel, start, outcome, event count."""
    print(LIST_HEADER)
    for row in store.sessions():
        started = time.strftime("%Y-%m-%d %H:%M", time.localtime(row.started_at))
        who = f"{row.tenant}/{row.project}"
        print(
            f"{row.id:<26} {who:<32} {row.channel:<7} {started:<16} {row.outcome or '-':<10} {row.event_count}"
        )
    return 0


def show_session(store: Store, session_id: str) -> int:
    """The seq table of one session; per-turn latencies rendered when the turn carries them."""
    row = store.session(session_id)
    if row is None:
        print(f"no session {session_id!r}")
        return 1
    print(f"{row.id}  {row.tenant}/{row.project}  {row.channel}  outcome={row.outcome or '-'}")
    print(SHOW_HEADER)
    for event in store.events(session_id):
        print(f"{event.seq:>4} {event.t_ms:>7}  {event.kind:<18} {render(event)}")
    return 0


def render(event: Event) -> str:
    """The payload on one line: latencies as `ttft=…` pairs, everything else as compact JSON."""
    payload = dict(event.payload)
    metrics: dict[str, Any] = payload.pop("metrics", None) or {}
    parts = [
        f"{k.replace('llm_node_', '').replace('_latency', '')}={metrics[k]:.2f}s"
        for k in METRIC_KEYS
        if isinstance(metrics.get(k), (int, float))
    ]
    if payload:
        parts.append(json.dumps(payload, ensure_ascii=False, default=str))
    return " ".join(parts)
