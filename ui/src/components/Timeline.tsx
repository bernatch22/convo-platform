/* The right-hand column: the runtime's own log, arriving while the call is still up.
 *
 * A transcript says what was said; this says what it cost to say it. Each
 * agent turn carries the five latencies the framework measured —
 * transcription_delay, end_of_turn_delay, llm_node_ttft, tts_node_ttfb,
 * e2e_latency — and they land WITH the turn, so a slow answer is visible
 * while the caller is still on the line instead of in a post-mortem.
 *
 * Every number here is the framework's own, in seconds, rendered as
 * milliseconds. Nothing is computed in the browser: if the log did not
 * measure it, the chip is simply absent.
 */

import { Link } from "react-router";

import type { SessionEvent } from "../lib/api";
import type { Timeline as Log } from "../lib/useTimeline";

/** The framework's metric names, in the order a turn spends its time, with the label shown. */
const METRICS: Array<[string, string]> = [
  ["transcription_delay", "stt"],
  ["end_of_turn_delay", "eot"],
  ["llm_node_ttft", "ttft"],
  ["tts_node_ttfb", "ttfb"],
  ["e2e_latency", "e2e"],
];

// `state` fires on every listening/thinking/speaking flip: true, and far too loud for a column.
const NOISE = new Set(["state", "tts.word"]);

export function Timeline({ log, tenant }: { log: Log; tenant: string }) {
  const rows = log.events.filter((event) => !NOISE.has(event.kind));

  return (
    <aside className="timeline">
      <div className="timeline__head">
        <span className="section__title">Timeline</span>
        <Status log={log} tenant={tenant} />
      </div>
      {rows.length === 0 ? (
        <p className="note">{waiting(log)}</p>
      ) : (
        <ol className="timeline__rows">
          {rows.map((event) => (
            <Row key={event.seq} event={event} />
          ))}
        </ol>
      )}
    </aside>
  );
}

function Status({ log, tenant }: { log: Log; tenant: string }) {
  if (!log.session) return <span className="badge">{log.status}</span>;
  return (
    <Link className="timeline__id" to={`/t/${tenant}/sessions/${log.session}`}>
      {log.session}
    </Link>
  );
}

function Row({ event }: { event: SessionEvent }) {
  return (
    <li className="row">
      <div className="row__top">
        <span className="row__kind">{event.kind}</span>
        <span className="row__t">{event.t_ms} ms</span>
      </div>
      {describe(event) && <p className="row__text">{describe(event)}</p>}
      <Chips payload={event.payload} />
    </li>
  );
}

function Chips({ payload }: { payload: Record<string, unknown> }) {
  const metrics = payload["metrics"];
  if (!metrics || typeof metrics !== "object") return null;
  const found = METRICS.map(([key, label]) => [label, (metrics as Record<string, unknown>)[key]])
    .filter((pair): pair is [string, number] => typeof pair[1] === "number")
    .map(([label, seconds]) => [label, Math.round(seconds * 1000)] as const);
  if (found.length === 0) return null;

  return (
    <div className="chips">
      {found.map(([label, ms]) => (
        <span className="chip" key={label}>
          <span className="chip__key">{label}</span>
          <span className="chip__val">{ms}</span>
        </span>
      ))}
    </div>
  );
}

/** The one sentence this event is worth on a live column, or "" when the kind says it all. */
function describe(event: SessionEvent): string {
  const payload = event.payload;
  switch (event.kind) {
    case "turn.user":
    case "turn.agent":
    case "stt.final":
      return text(payload["text"]);
    case "tool.call":
    case "tool.result":
    case "tool.refused":
    case "tool.error":
      return [text(payload["tool"]), text(payload["reason"] ?? payload["side_effect"])]
        .filter(Boolean)
        .join(" · ");
    case "stage.enter":
      return text(payload["stage"]);
    case "session.start":
      return `${text(payload["tenant"])} / ${text(payload["project"])} · ${text(payload["channel"])}`;
    case "session.end":
      return text(payload["outcome"]);
    case "error":
      return text(payload["error"]);
    default:
      return "";
  }
}

function waiting(log: Log): string {
  if (log.status === "off") return "no session open";
  if (log.status === "finding") return "matching this room to its session…";
  return "the log is open and empty — the first turn writes to it";
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}
