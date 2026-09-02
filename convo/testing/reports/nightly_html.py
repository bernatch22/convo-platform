"""The page a nightly leaves behind: every score next to the call that produced it.

Decisions: docs/decisions/convo.testing.reports.nightly_html.md
"""

from html import escape
from typing import Any

STYLE = """
:root { color-scheme: light dark; --ink:#111; --dim:#666; --line:#ddd; --ok:#0a7d3f; --bad:#b3261e;
        --wash:rgba(127,127,127,.08) }
@media (prefers-color-scheme: dark) { :root { --ink:#e8e8e8; --dim:#9a9a9a; --line:#333 } }
body { font: 15px/1.55 -apple-system, system-ui, sans-serif; color: var(--ink);
       max-width: 62rem; margin: 3rem auto; padding: 0 1.5rem }
h1 { font-size: 1.6rem; margin-bottom: .2rem } h2 { font-size: 1.15rem; margin-top: 2.6rem }
h3 { font-size: .95rem; margin: 1.6rem 0 .4rem }
p.sub { color: var(--dim); margin-top: 0 }
table { border-collapse: collapse; width: 100%; font-size: .88rem; margin: .8rem 0 }
th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid var(--line);
         vertical-align: top }
th { color: var(--dim); font-weight: 600 }
td.n { text-align: right; font-variant-numeric: tabular-nums }
.pass { color: var(--ok) } .fail { color: var(--bad); font-weight: 600 }
.note { border-left: 3px solid var(--bad); padding: .1rem 0 .1rem 1rem; color: var(--dim) }
.turns { background: var(--wash); border-radius: 6px; padding: .7rem 1rem; font-size: .87rem }
.turns div { margin: .25rem 0 } .turns b { color: var(--dim); font-weight: 600 }
.reason { color: var(--dim); font-size: .85rem }
code { font: 13px/1.5 ui-monospace, Menlo, monospace }
"""


def page(
    *,
    date: str,
    git: str,
    budget: int,
    spent: int,
    suites: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> str:
    """The whole night as one self-contained HTML file."""
    red = [suite for suite in suites if suite["status"] != "done"]
    verdict = (
        f"<span class='fail'>{len(red)} red</span>" if red else "<span class='pass'>green</span>"
    )
    return (
        f"<!doctype html><meta charset='utf-8'>"
        f"<title>ring 2 · {escape(date)}</title><style>{STYLE}</style>"
        f"<h1>Ring 2 · {escape(date)}</h1>"
        f"<p class='sub'>{verdict} · {spent}/{budget} conversations · "
        f"<code>{escape(git)}</code></p>"
        f"{_skipped(skipped)}{_summary(suites)}" + "".join(_suite(suite) for suite in suites)
    )


def _skipped(skipped: list[dict[str, Any]]) -> str:
    """The suites the budget refused, named — a night that skipped one is not a green night."""
    if not skipped:
        return ""
    named = ", ".join(f"{escape(row['id'])} ({row['calls']} calls)" for row in skipped)
    return (
        f"<p class='note'><b>Skipped by the budget:</b> {named}. The cap is a decision, "
        "so the run is red until somebody raises it on purpose or drops a golden.</p>"
    )


def _summary(suites: list[dict[str, Any]]) -> str:
    """One row per suite: the table a person reads before deciding whether to read further."""
    rows = "".join(
        f"<tr><td>{escape(suite['id'])}</td>"
        f"<td class='{_tone(suite['status'] == 'done')}'>{escape(suite['status'])}</td>"
        f"<td class='n'>{suite['calls']}</td>"
        f"<td class='n pass'>{suite['passed']}</td>"
        f"<td class='n {_tone(not suite['failed'])}'>{suite['failed']}</td>"
        f"<td>{_worst(suite['worst'])}</td>"
        f"<td class='n'>{suite['seconds']:.0f}s</td>"
        f"<td class='n'>${suite['judge_usd']:.4f}</td></tr>"
        for suite in suites
    )
    return (
        "<table><tr><th>suite<th>status<th>calls<th>passed<th>failed<th>worst metric"
        f"<th>took<th>judge</tr>{rows}</table>"
    )


def _suite(suite: dict[str, Any]) -> str:
    """One project's section: its metrics, then every call with the verdicts it earned."""
    detail = f"<p class='note'>{escape(suite['detail'])}</p>" if suite["detail"] else ""
    metrics = "".join(
        f"<tr><td>{escape(row['metric'])}</td><td class='n'>{row['score']:.3f}</td>"
        f"<td class='n pass'>{row['passed']}</td>"
        f"<td class='n {_tone(not row['failed'])}'>{row['failed']}</td></tr>"
        for row in suite["metrics"]
    )
    table = (
        f"<table><tr><th>metric<th>mean<th>passed<th>failed</tr>{metrics}</table>"
        if metrics
        else "<p class='note'>The suite scored nothing — it did not get that far.</p>"
    )
    return f"<h2>{escape(suite['id'])}</h2>{detail}{table}" + "".join(
        _case(case) for case in suite["cases"]
    )


def _case(case: dict[str, Any]) -> str:
    """One call: what it was asked to prove, how each metric judged it, and what was said."""
    name = escape(str(case.get("name") or "unnamed"))
    ok = bool(case.get("success"))
    flaky = " · flaky" if case.get("flaky") else ""
    scenario = case.get("scenario")
    intro = f"<p class='reason'>{escape(str(scenario))}</p>" if scenario else ""
    return (
        f"<h3><span class='{_tone(ok)}'>{'PASS' if ok else 'FAIL'}</span> {name}{flaky}</h3>"
        f"{intro}{_verdicts(case.get('metricsData') or [])}{_turns(case)}"
    )


def _verdicts(rows: list[dict[str, Any]]) -> str:
    """Every metric's score, threshold and reason for one call — the red ones read first."""
    if not rows:
        return ""
    ordered = sorted(rows, key=lambda row: bool(row.get("success")))
    cells = "".join(
        f"<tr><td>{escape(str(row.get('name', '?')))}</td>"
        f"<td class='n {_tone(bool(row.get('success')))}'>"
        f"{float(row.get('score') or 0):.2f}</td>"
        f"<td class='n'>{float(row.get('threshold') or 0):.2f}</td>"
        f"<td class='reason'>{escape(str(row.get('reason') or ''))}</td></tr>"
        for row in ordered
    )
    return f"<table><tr><th>metric<th>score<th>threshold<th>reason</tr>{cells}</table>"


def _turns(case: dict[str, Any]) -> str:
    """What both sides actually said, in order — the half of a red score the log alone gives."""
    turns = case.get("turns") or []
    if not turns:
        spoken = case.get("actualOutput")
        return f"<div class='turns'>{escape(str(spoken))}</div>" if spoken else ""
    lines = "".join(
        f"<div><b>{escape(str(turn.get('role', '?')))}</b> "
        f"{escape(str(turn.get('content') or ''))}</div>"
        for turn in turns
    )
    return f"<div class='turns'>{lines}</div>"


def _worst(low: dict[str, Any] | None) -> str:
    """The lowest failing metric of a suite, as the cell the summary table shows."""
    if not low:
        return "-"
    tone = _tone(not low["failed"])
    return f"<span class='{tone}'>{escape(low['metric'])} {low['score']:.3f}</span>"


def _tone(ok: bool) -> str:
    """`pass` or `fail` — the only two colours this page has."""
    return "pass" if ok else "fail"
