"""The ms-6 voice report: one recorded call, its event table, its scores, its golden.

Decisions: docs/decisions/convo.testing.reports.voice_report.md
"""

import json
import shutil
import statistics
import sys
from pathlib import Path

from convo.state.events import Event
from convo.state.store import SQLiteStore, Store
from convo.testing.callers.audio import recorded_path, voice_case_from
from convo.testing.reports.voice_report_html import page

OUT = Path("tmp/reports")
GOLDEN = Path("tmp/golden/golden.json")


def build(session_id: str, store: Store, out: Path = OUT) -> Path:
    """Write the report for one recorded session and return the file it wrote."""
    row = store.session(session_id)
    if row is None:
        raise LookupError(f"no session {session_id!r} in this store")
    events = store.events(session_id)
    assets = _copy_assets(events, out)
    html = page(
        row=row,
        events=events,
        turns=turn_rows(events),
        p50=p50_answer(events),
        metrics=scores(store, session_id),
        golden=json.loads(GOLDEN.read_text()) if GOLDEN.exists() else None,
        assets=assets,
    )
    out.mkdir(parents=True, exist_ok=True)
    target = out / "ms-6.html"
    target.write_text(html)
    return target


def turn_rows(events: list[Event]) -> list[dict]:
    """One row per agent turn: when it took the floor, its latencies, what it said."""
    rows: list[dict] = []
    asked: int | None = None
    speaking: int | None = None
    for event in events:
        if event.kind == "turn.user":
            asked = event.t_ms
        elif event.kind == "state" and event.payload.get("to") == "speaking":
            speaking = event.t_ms
        elif event.kind == "turn.agent":
            metrics = event.payload.get("metrics") or {}
            floor = speaking if speaking is not None else event.t_ms
            answer = (floor - asked) / 1000 if asked is not None and floor > asked else None
            rows.append(
                {
                    "from_ms": floor,
                    "to_ms": event.t_ms,
                    "ttft": metrics.get("llm_node_ttft"),
                    "ttfb": metrics.get("tts_node_ttfb"),
                    "answer_s": answer,
                    "words": 0,
                    "text": event.payload.get("text", "").strip(),
                }
            )
            asked = speaking = None
    _count_words(events, rows)
    return rows


def p50_answer(events: list[Event]) -> float | None:
    """The median caller-line-to-first-sound latency of the call, or None with no answers."""
    values = [row["answer_s"] for row in turn_rows(events) if row["answer_s"] is not None]
    return round(statistics.median(values), 2) if values else None


def scores(store: Store, session_id: str) -> list[dict]:
    """Both offline voice metrics on the recording: score, threshold, reason, defects."""
    from deepeval.metrics.voice import AgentResponsivenessMetric, AudioIntegrityMetric

    case = voice_case_from(store, session_id)
    measured = []
    for metric in (AudioIntegrityMetric(flaky=True), AgentResponsivenessMetric(flaky=True)):
        metric.measure(case, _show_indicator=False)
        measured.append(
            {
                "name": metric.__name__,
                "score": metric.score,
                "threshold": metric.threshold,
                "reason": metric.reason,
                "events": metric.score_breakdown["events"],
            }
        )
    return measured


def main(argv: list[str]) -> int:
    """CLI: one session id; writes tmp/reports/ms-6.html and prints where it went."""
    if len(argv) < 2:
        print("usage: python -m core.testing.voice_report <session-id>")
        return 2
    print(build(argv[1], SQLiteStore()))
    return 0


def _copy_assets(events: list[Event], out: Path) -> dict[str, str]:
    """Put the OGG and the golden WAVs next to the HTML so the page is one directory."""
    out.mkdir(parents=True, exist_ok=True)
    media = out / "ms-6"
    media.mkdir(exist_ok=True)
    assets: dict[str, str] = {}
    ogg = recorded_path(events)
    if ogg and Path(ogg).exists():
        shutil.copy(ogg, media / "audio.ogg")
        assets["ogg"] = "ms-6/audio.ogg"
    for wav in sorted(Path("tmp/golden").glob("*.wav")):
        shutil.copy(wav, media / wav.name)
        assets[wav.stem] = f"ms-6/{wav.name}"
    return assets


def _count_words(events: list[Event], rows: list[dict]) -> None:
    """Attribute each `tts.word` batch to the turn whose window it falls in."""
    for event in events:
        if event.kind != "tts.word":
            continue
        for row in rows:
            if row["from_ms"] <= event.t_ms <= row["to_ms"]:
                row["words"] += len(event.payload.get("words") or [])
                break


if __name__ == "__main__":
    sys.exit(main(sys.argv))
