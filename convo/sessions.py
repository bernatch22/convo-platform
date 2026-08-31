"""`convo sessions`: list recorded sessions, show one as its seq table, or score one."""

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
USAGE = "usage: python -m convo sessions list | show <id> | eval <id> [--voice]"
NODE_LINES = ("Label:", "Verdict:", "Reason:")
WIDTH = 160

SILENT_CALLER = (
    "voice note: only the agent's channel carries sound on an offline recording — the caller "
    "typed. Integrity reads assistant audio only, so it is unaffected; responsiveness checks "
    "that each answer HAS audio, which it does. docs/evals.md §3.9."
)

BLIND_SPOT = (
    "ring 3 note: {tools} declares no result summary on its ToolSpec, so the log kept the "
    "shape of what it returned and not its contents. A fact the agent read off one of them "
    "reaches the judge with evidence that could not contain it — read a 0.0 on such a claim "
    "as 'not verifiable from the log', not as an invention. docs/evals.md §3.6."
)


def main(argv: list[str], store: Store | None = None) -> int:
    """`list` prints every session newest first; `show`/`eval <id>` read or score one."""
    store = store or SQLiteStore()
    if argv[:1] == ["list"]:
        return list_sessions(store)
    if argv[:1] == ["show"] and len(argv) == 2:
        return show_session(store, argv[1])
    if argv[:1] == ["eval"] and len(argv) in (2, 3):
        return eval_session(store, argv[1], voice="--voice" in argv[2:])
    print(USAGE)
    return 2


def list_sessions(store: Store) -> int:
    """One line per session: id, tenant/project, channel, start, outcome, event count."""
    print(LIST_HEADER)
    for row in store.sessions():
        started = time.strftime("%Y-%m-%d %H:%M", time.localtime(row.started_at))
        who = f"{row.tenant}/{row.project}"
        outcome = row.outcome or "-"
        line = f"{row.id:<26} {who:<32} {row.channel:<7} {started:<16} {outcome:<10}"
        print(f"{line} {row.event_count}")
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


def eval_session(store: Store, session_id: str, voice: bool = False) -> int:
    """Score one stored session with its own project's conversational metrics (ring 3).

    The same metrics the CI suite runs on goldens, on a call that really
    happened: the log becomes a `ConversationalTestCase` and each metric prints
    its score, its threshold and why. What the replay could not see is printed
    with the score that suffers from it, never left for the reader to work out.
    """
    row = store.session(session_id)
    if row is None:
        print(f"no session {session_id!r}")
        return 1
    # Imported here, not at the top: deepeval pulls in a judge stack, and
    # `sessions list` on a laptop should not pay a second for it.
    from core.testing import replay
    from core.testing.deepeval import project_metrics

    descriptions = replay.descriptions_for(row.tenant, row.project)
    case = replay.conversational_case_from(store, session_id, descriptions)
    metrics = project_metrics(row.tenant, row.project)
    print(f"{row.id}  {row.tenant}/{row.project}  {row.channel}  outcome={row.outcome or '-'}")
    print(f"{len(case.turns)} turns replayed from {row.event_count} events")
    blind = replay.missing_tool_outputs(case)
    note = BLIND_SPOT.format(tools=_and(blind)) if blind else None
    score(metrics.consent_policy(), case)
    score(metrics.grounded_facts_dag(), case, note=note)
    if voice:
        score_voice(store, session_id)
    return 0


def score_voice(store: Store, session_id: str) -> int:
    """Score the recording of a session with the two offline voice metrics (ms-6).

    They are detectors, not judges: `AudioIntegrityMetric` measures the agent's
    own audio (clipping, dropouts, loops, an abrupt cutoff) and
    `AgentResponsivenessMetric` reads the shape of the turns and whether every
    answer arrived with sound. Neither calls a model, so this costs nothing and
    needs no key — only the OGG the session recorded.
    """
    from deepeval.metrics.voice import AgentResponsivenessMetric, AudioIntegrityMetric

    from core.testing.audio import recorded_path, voice_case_from

    path = recorded_path(store.events(session_id))
    if not path:
        print(f"\n{session_id} was not recorded: no voice metrics to run.")
        return 1
    case = voice_case_from(store, session_id, path)
    spoken = sum(1 for turn in case.turns if turn.audio is not None)
    print(f"\naudio {path} — {spoken} of {len(case.turns)} turns carry sound")
    print(SILENT_CALLER)
    for metric in (AudioIntegrityMetric(), AgentResponsivenessMetric()):
        score(metric, case)
    return 0


def score(metric: Any, case: Any, note: str | None = None) -> float:
    """Measure one metric on the replayed case and print the verdict, the caveat, the reason."""
    value = metric.measure(case)
    verdict = "PASS" if value >= metric.threshold else "FAIL"
    print(f"\n{metric.__name__}: {value} (threshold {metric.threshold}) {verdict}")
    if note:
        print(f"  {note}")
    for line in _explanation(metric):
        print(f"  {line}")
    return value


def render(event: Event) -> str:
    """The payload on one line: timed words as `word@t`, latencies as `ttft=…`, rest as JSON."""
    payload = dict(event.payload)
    words: list[dict[str, Any]] = payload.pop("words", None) or []
    metrics: dict[str, Any] = payload.pop("metrics", None) or {}
    parts = [
        f"{k.replace('llm_node_', '').replace('_latency', '')}={metrics[k]:.2f}s"
        for k in METRIC_KEYS
        if isinstance(metrics.get(k), (int, float))
    ]
    parts.extend(f"{word['w']}@{word['t1']:.2f}" for word in words if "t1" in word)
    if payload:
        parts.append(json.dumps(payload, ensure_ascii=False, default=str))
    return " ".join(parts)


def _explanation(metric: Any) -> list[str]:
    """A metric's reason, or — for one built with `include_reason=False` — its node chain.

    DeepEval's verbose log is the whole graph: every criterion, every rendered
    block, the clinic's information sheet in full. An operator asking why a call
    scored 0.0 wants the labels and the one-line reason each node wrote, so that
    is what is kept and the rest is left for `deepeval test run -v`.
    """
    if getattr(metric, "reason", None):
        return [_short(str(metric.reason))]
    lines = str(getattr(metric, "verbose_logs", "") or "").splitlines()
    return [_short(line.strip()) for line in lines if line.strip().startswith(NODE_LINES)]


def _short(line: str) -> str:
    """One line of at most `WIDTH` characters: a judge's paragraph is not a terminal line."""
    return line if len(line) <= WIDTH else line[: WIDTH - 1] + "…"


def _and(names: list[str]) -> str:
    """`a`, `a and b`, `a, b and c` — a list a sentence can contain."""
    if len(names) < 2:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]
