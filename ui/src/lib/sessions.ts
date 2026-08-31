/* Everything the two session screens READ out of a log, and nothing they draw.
 *
 * The CLI (`python -m convo sessions show <id>`) and these screens must print
 * the same numbers off the same events, so the arithmetic lives here once,
 * in the CLI's units: seconds to two decimals, medians over the turns that
 * actually carry a metric. A never-measured leg is null, never 0 — a zero
 * would read as "instant" when it means "nobody looked".
 */

import type { SessionEvent, SessionLine, SessionScore, SessionView } from "./api";

/** What a row of the call log says it is: a browser call, a chat, or the telephone. */
export type Medium = "voice" | "chat" | "phone";

/** The legs the log times, named as the CLI abbreviates them.
 *
 * The first four are exactly what `sessions show` prints per turn, so the
 * strip over them is checkable against the terminal line by line. `ttfb` is in
 * the payload and the CLI does not print it; it is shown last, and the screen
 * says so, because hiding a measured number is the worse of the two lies.
 */
export const LATENCY_LEGS = ["ttft", "e2e", "eot", "stt", "ttfb"] as const;

export type LatencyLeg = (typeof LATENCY_LEGS)[number];

/** Where each leg's seconds live inside `payload.metrics`. */
const METRIC_OF: Record<LatencyLeg, string> = {
  ttft: "llm_node_ttft",
  e2e: "e2e_latency",
  eot: "end_of_turn_delay",
  stt: "transcription_delay",
  ttfb: "tts_node_ttfb",
};

/** The label each leg wears on screen, in the words the terminal already uses. */
export const LEG_LABEL: Record<LatencyLeg, string> = {
  ttft: "ttft",
  e2e: "e2e",
  eot: "end_of_turn_delay",
  stt: "transcription_delay",
  ttfb: "tts_node_ttfb",
};

/** Median, max and the sample size behind them; nulls when no turn carried the leg. */
export interface LegStat {
  leg: LatencyLeg;
  median: number | null;
  max: number | null;
  turns: number;
}

/** One granted consent and the irreversible call it paid for — the audit's load-bearing link. */
export interface ConsentLink {
  audience: string;
  tool: string;
  requested: number | null;
  granted: number | null;
  declined: number | null;
  authorised: number | null;
  sideEffect: string | null;
}

/** One model's slice of the bill, as `session.end` priced it. */
export interface CostLine {
  provider: string;
  model: string;
  eur: number;
}

/** The telephone's own metadata: the two numbers, and the whole `sip.*` map behind them. */
export interface SipView {
  caller: string | null;
  dialled: string | null;
  attributes: [string, string][];
}

/* ── the call log's row ───────────────────────────────────────────────────── */

/** Voice over the telephone or voice in a browser: the `phone` field is the only tell. */
export function mediumOf(line: Pick<SessionLine, "channel" | "phone">): Medium {
  return line.phone ? "phone" : line.channel;
}

/** `14:32` for today, `Aug 29 14:32` otherwise — an operator scans the time, not the year. */
export function startedAt(seconds: number): string {
  const at = new Date(seconds * 1000);
  const clock = at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (at.toDateString() === new Date().toDateString()) return clock;
  const day = at.toLocaleDateString(undefined, { month: "short", day: "2-digit" });
  return `${day} ${clock}`;
}

/** `1m 04s` — how long the call lasted, or null while it is still running. */
export function duration(line: Pick<SessionLine, "started_at" | "ended_at">): string | null {
  if (line.ended_at === null) return null;
  const total = Math.max(0, Math.round(line.ended_at - line.started_at));
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
}

/** Four decimals, because a whole call costs less than a cent and 0.00 € is a lie. */
export function euros(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(4)} €`;
}

/** What a score chip says on hover — including what a dash means, which is the harder half.
 *
 * Three different facts share the dash, and an operator scanning a column of
 * them needs to know which one they are looking at: a call still running has
 * not ended, one that ended a second ago is queued behind the sweeper, and one
 * whose project opted out will never have a score at all. The console cannot
 * tell the last two apart from the row alone — the API returns null for both —
 * so the tooltip names both possibilities rather than guessing at one.
 */
export function scoreTitle(score: SessionScore | null, running?: boolean): string {
  if (running) return "The call is still going: it is scored once it ends.";
  if (!score) {
    return "No score yet — either the control plane has not reached it, or this project has scoring switched off.";
  }
  const judged = score.judge?.ran ? `judged by ${score.judge.model}` : "deterministic checks only";
  const failed = score.failed.length > 0 ? ` — failed: ${score.failed.join(", ")}` : "";
  return `${score.verdict} ${score.score.toFixed(2)} over ${score.checks.length} checks, ${judged}${failed}`;
}

/** Seconds the way the CLI prints them: `1.73s`, or an em dash when nothing was measured. */
export function seconds(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(2)}s`;
}

/* ── the latency strip ───────────────────────────────────────────────────── */

/** Median and max of every leg across this session's turns — the strip, in one pass.
 *
 * Median of an even sample is the mean of the two middle values, which is why
 * a four-turn session can show a `ttft` no single turn printed. Every number
 * here is one the CLI already showed per turn; this only aggregates them.
 */
export function latencyStrip(events: SessionEvent[]): LegStat[] {
  return LATENCY_LEGS.map((leg) => {
    const samples = metricSamples(events, METRIC_OF[leg]);
    return { leg, median: median(samples), max: maxOf(samples), turns: samples.length };
  });
}

/** The metric chips one turn earned, in the CLI's order, ready to render. */
export function turnChips(event: SessionEvent): { label: string; value: string }[] {
  const metrics = asRecord(event.payload["metrics"]);
  if (!metrics) return [];
  const order: [string, string][] = [
    ["llm_node_ttft", "ttft"],
    ["tts_node_ttfb", "ttfb"],
    ["e2e_latency", "e2e"],
    ["transcription_delay", "transcription_delay"],
    ["end_of_turn_delay", "end_of_turn_delay"],
  ];
  return order
    .filter(([key]) => typeof metrics[key] === "number")
    .map(([key, label]) => ({ label, value: `${(metrics[key] as number).toFixed(2)}s` }));
}

/* ── the consent proof ───────────────────────────────────────────────────── */

/** Every confirmation this call asked for, and the irreversible call each one authorised.
 *
 * `ConfirmTask` mints an audience per question (`<tool>:<hash>`), so the grant
 * and the request are joinable by it; the tool call it paid for is the first
 * `tool.call` for that tool AFTER the grant. A request with no grant and no
 * refusal is a call that hung up mid-question — it is listed, unlinked, which
 * is exactly what happened.
 */
export function consentLinks(events: SessionEvent[]): ConsentLink[] {
  const links = new Map<string, ConsentLink>();
  for (const event of events) {
    if (!event.kind.startsWith("confirm.")) continue;
    const tool = text(event.payload["tool"]) ?? "?";
    const audience = text(event.payload["audience"]) ?? `${tool}:${event.seq}`;
    const link = links.get(audience) ?? blankLink(audience, tool);
    if (event.kind === "confirm.request") link.requested = event.seq;
    if (event.kind === "confirm.granted") link.granted = event.seq;
    if (event.kind === "confirm.declined") link.declined = event.seq;
    links.set(audience, link);
  }
  for (const link of links.values()) {
    if (link.granted === null) continue;
    const call = events.find(
      (e) => e.kind === "tool.call" && e.seq > link.granted! && text(e.payload["tool"]) === link.tool,
    );
    link.authorised = call?.seq ?? null;
    link.sideEffect = call ? text(call.payload["side_effect"]) : null;
  }
  return [...links.values()].sort((a, b) => order(a) - order(b));
}

/** The seq that authorised this one, when the log says a grant paid for it. */
export function authorisedBy(links: ConsentLink[], seq: number): ConsentLink | null {
  return links.find((link) => link.authorised === seq) ?? null;
}

/* ── the envelope: sip, cost, report ─────────────────────────────────────── */

/** The `sip.*` map off `session.start`, split into the two numbers and the rest. */
export function sipOf(events: SessionEvent[]): SipView | null {
  const start = events.find((event) => event.kind === "session.start");
  const sip = start ? asRecord(start.payload["sip"]) : null;
  if (!sip) return null;
  return {
    caller: text(sip["sip.phoneNumber"]),
    dialled: text(sip["sip.trunkPhoneNumber"]),
    attributes: Object.entries(sip)
      .map(([key, value]) => [key, String(value)] as [string, string])
      .sort((a, b) => a[0].localeCompare(b[0])),
  };
}

/** What each model charged, off the `session.end` event that closed the call. */
export function costLines(events: SessionEvent[]): CostLine[] {
  const end = events.find((event) => event.kind === "session.end");
  const cost = end ? asRecord(end.payload["cost"]) : null;
  const models = cost ? cost["models"] : null;
  if (!Array.isArray(models)) return [];
  return models.flatMap((entry) => {
    const row = asRecord(entry);
    if (!row || typeof row["eur"] !== "number") return [];
    return [
      { provider: text(row["provider"]) ?? "?", model: text(row["model"]) ?? "?", eur: row["eur"] },
    ];
  });
}

/** Why the call ended, in the log's own word (`participant_disconnected`, `user_initiated`, …). */
export function endReason(events: SessionEvent[]): string | null {
  const end = events.find((event) => event.kind === "session.end");
  return end ? text(end.payload["reason"]) : null;
}

/** The stages this call walked through, in order — the process, read off the log. */
export function stagesOf(view: SessionView): string[] {
  const seen: string[] = [];
  for (const event of view.events_log) {
    const stage = event.kind === "stage.enter" ? text(event.payload["stage"]) : null;
    if (stage && seen[seen.length - 1] !== stage) seen.push(stage);
  }
  return seen;
}

/* ── the small print ─────────────────────────────────────────────────────── */

function blankLink(audience: string, tool: string): ConsentLink {
  return {
    audience,
    tool,
    requested: null,
    granted: null,
    declined: null,
    authorised: null,
    sideEffect: null,
  };
}

function order(link: ConsentLink): number {
  return link.requested ?? link.granted ?? link.declined ?? 0;
}

function metricSamples(events: SessionEvent[], key: string): number[] {
  const found: number[] = [];
  for (const event of events) {
    const metrics = asRecord(event.payload["metrics"]);
    const value = metrics ? metrics[key] : undefined;
    if (typeof value === "number") found.push(value);
  }
  return found;
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  const high = sorted[middle] as number;
  return sorted.length % 2 === 1 ? high : (((sorted[middle - 1] as number) + high) / 2);
}

function maxOf(values: number[]): number | null {
  return values.length === 0 ? null : Math.max(...values);
}

/** A payload field that should be an object, or null — the log is JSON, not a type. */
export function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** A payload field that should be a string, or null. */
export function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}
