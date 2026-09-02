"""The HTML of the ms-6 voice report: one page, no assets but the audio next to it.

Decisions: docs/decisions/convo.testing.reports.voice_report_html.md
"""

from typing import Any

STYLE = """
:root { color-scheme: light dark; --ink:#111; --dim:#666; --line:#ddd; --ok:#0a7d3f; --bad:#b3261e }
@media (prefers-color-scheme: dark) { :root { --ink:#e8e8e8; --dim:#9a9a9a; --line:#333 } }
body { font: 15px/1.55 -apple-system, system-ui, sans-serif; color: var(--ink);
       max-width: 60rem; margin: 3rem auto; padding: 0 1.5rem }
h1 { font-size: 1.6rem; margin-bottom: .2rem } h2 { font-size: 1.1rem; margin-top: 2.5rem }
p.sub { color: var(--dim); margin-top: 0 }
table { border-collapse: collapse; width: 100%; font-size: .88rem; margin: .8rem 0 }
th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid var(--line) }
th { color: var(--dim); font-weight: 600 }
td.n { text-align: right; font-variant-numeric: tabular-nums }
.note { border-left: 3px solid var(--line); padding: .1rem 0 .1rem 1rem; color: var(--dim) }
.pass { color: var(--ok) } .fail { color: var(--bad) }
code, pre { font: 13px/1.5 ui-monospace, Menlo, monospace }
pre { background: rgba(127,127,127,.1); padding: .8rem 1rem; overflow-x: auto; border-radius: 6px }
audio { width: 100%; margin: .5rem 0 }
"""

CAVEATS = """
<p class="note"><b>Léelo con esto delante.</b> El llamante nunca habló: sus líneas
se escribieron, y solo el canal del agente del OGG lleva sonido. Por eso <b>no hay
eventos <code>stt.final</code></b> ni <code>e2e_latency</code> del framework — esa
se mide desde un fin de habla que un turno escrito no tiene. <i>answer</i> es el
sustituto honesto: de la línea del llamante al primer sonido del agente, ambos
leídos del mismo reloj de sesión. La otra mitad la da
<code>python worker.py console --record</code>, que necesita una persona con
micrófono.</p>
"""

DROPOUTS = """
<p class="note"><b>Por qué Audio Integrity da 0.00.</b> Su detector cuenta como
<code>audio_dropout</code> cualquier silencio de 20–200 ms rodeado de voz
(<code>deepeval/metrics/voice/_analysis.py</code>, umbral fijo RMS 300). En un clip
de una frase eso es un corte; en un turno conversacional de 5–12 s son las pausas
entre palabras, y tres bastan para agotar la penalización. Lo que sí significa algo
está en la tabla y en el breakdown: ningún fallo crítico, cero
<code>clipping</code>, cero <code>audio_loop</code>, cero <code>audio_missing</code>
y ningún <code>abrupt_cutoff</code>. La puntuación se lee como un semáforo roto; el
desglose, no.</p>
"""


def page(*, row, events, turns, p50, metrics, golden, assets) -> str:
    """The whole report as one HTML string."""
    return f"""<!doctype html><html lang="es"><meta charset="utf-8">
<title>ms-6 — voz local</title><style>{STYLE}</style>
<h1>ms-6 · voz local, medida en frío</h1>
<p class="sub">{row.tenant}/{row.project} · {row.channel} · sesión <code>{row.id}</code> ·
{row.event_count} eventos · outcome {row.outcome or "-"}</p>
{CAVEATS}
{_audio(assets)}
{_turns(turns, p50)}
{_metrics(metrics)}
{_golden(golden, assets)}
{_commands(row.id)}
</html>"""


def _audio(assets: dict[str, str]) -> str:
    if "ogg" not in assets:
        return "<h2>La llamada</h2><p class='note'>No se copió el OGG.</p>"
    return (
        "<h2>La llamada</h2>"
        "<p>Estéreo, 48 kHz, Opus. Izquierda = llamante (silencio), derecha = agente.</p>"
        f'<audio controls src="{assets["ogg"]}"></audio>'
    )


def _turns(turns: list[dict], p50: float | None) -> str:
    rows = "".join(
        "<tr>"
        f"<td class='n'>{turn['from_ms'] / 1000:.2f}s</td>"
        f"<td class='n'>{(turn['to_ms'] - turn['from_ms']) / 1000:.2f}s</td>"
        f"<td class='n'>{_s(turn['ttft'])}</td><td class='n'>{_s(turn['ttfb'])}</td>"
        f"<td class='n'>{_s(turn['answer_s'])}</td><td class='n'>{turn['words']}</td>"
        f"<td>{turn['text']}</td></tr>"
        for turn in turns
    )
    median = f"{p50:.2f}s" if p50 is not None else "—"
    return (
        "<h2>Turnos del agente</h2><table><tr><th>empieza</th><th>dura</th>"
        "<th>llm ttft</th><th>tts ttfb</th><th>answer</th><th>tts.word</th><th>texto</th></tr>"
        f"{rows}</table>"
        f"<p><b>p50 answer = {median}</b> — mediana de la latencia línea del llamante → primer "
        "sonido del agente, sin contar el saludo (no responde a nadie).</p>"
    )


def _metrics(metrics: list[dict]) -> str:
    blocks = []
    for metric in metrics:
        verdict = "pass" if (metric["score"] or 0) >= metric["threshold"] else "fail"
        defects = _defects(metric["events"])
        blocks.append(
            f"<p><b>{metric['name']}</b>: <span class='{verdict}'>{metric['score']:.2f}</span> "
            f"(umbral {metric['threshold']}) — {metric['reason']}</p>{defects}"
        )
    return "<h2>Métricas de voz (DeepEval 4.2, sin juez)</h2>" + "".join(blocks) + DROPOUTS


def _defects(events: list[dict]) -> str:
    if not events:
        return ""
    rows = "".join(
        f"<tr><td>{event['type']}</td><td class='n'>{event.get('turn', '')}</td>"
        f"<td class='n'>{event.get('count', '')}</td>"
        f"<td>{'crítico' if event.get('critical') else 'no'}</td></tr>"
        for event in events
    )
    return f"<table><tr><th>defecto</th><th>turno</th><th>n</th><th>crítico</th></tr>{rows}</table>"


def _golden(golden: dict[str, Any] | None, assets: dict[str, str]) -> str:
    if not golden:
        return ""
    rows, players = "", ""
    for model, data in golden["models"].items():
        spans = " · ".join(f"{k}={_s(v)}" for k, v in data["spans"].items())
        rows += (
            f"<tr><td>{model}</td><td class='n'>{data['ttfb_s']:.3f}s</td>"
            f"<td class='n'>{data['audio_s']:.2f}s</td><td class='n'>{data['control_s']:.2f}s</td>"
            f"<td class='n'>{data['read_out']:.0%}</td><td>{spans}</td></tr>"
        )
        for label, key in ((model, model), (f"{model} · control deletreado", f"{model}-control")):
            if key in assets:
                players += f"<p>{label}</p><audio controls src='{assets[key]}'></audio>"
    return (
        f"<h2>Golden de TTS</h2><p><code>{golden['golden']}</code></p>"
        "<table><tr><th>modelo</th><th>ttfb</th><th>audio</th><th>control deletreado</th>"
        f"<th>leído</th><th>tramos alineados</th></tr>{rows}</table>"
        "<p class='note'>El transcript alineado devuelve el texto de ENTRADA (los dígitos sin "
        "expandir), así que no puede probar cómo se leyó un número. Lo que sí lo prueba es la "
        "duración: la misma frase con el DNI, el importe y la hora ya escritos en palabras dura "
        "lo mismo o menos. Los tramos por token son relativos a su chunk de websocket y "
        "<code>—</code> marca el que cruzó uno.</p>" + players
    )


def _commands(session_id: str) -> str:
    return f"""<h2>Para reproducirlo</h2><pre>
python worker.py console --record   # con micrófono, la de verdad
python -m core.testing.record clinica-norte reagendamiento   # sin micrófono, la de aquí
python -m convo sessions show {session_id}
python -m convo sessions eval {session_id} --voice
python -m core.testing.tts_golden
python -m core.testing.voice_report {session_id}
pytest -m unit tests/test_audio_split.py
deepeval test run tests/evals/test_voice_deepeval.py</pre>"""


def _s(value: float | None) -> str:
    """A number of seconds, or an em dash where the log has none."""
    return f"{value:.2f}s" if isinstance(value, (int, float)) else "—"
