/* One line of the append-only log, drawn as what it is rather than as JSON.
 *
 * Same rows, same order, same numbers as `python -m convo sessions show <id>`;
 * only the rendering differs, and only where a shape earns it — a turn shows
 * its metric chips, a tool call its (already masked) arguments, a grant the
 * seq it authorised. Anything this file has no opinion about falls through to
 * the raw payload, so a kind added tomorrow is legible today.
 */

import { asRecord, text, turnChips, type ConsentLink } from "../lib/sessions";
import type { SessionEvent } from "../lib/api";

/** The visual family a kind belongs to: it decides the row's rule colour, nothing else. */
export type Family =
  | "turn"
  | "tool"
  | "consent"
  | "stage"
  | "state"
  | "envelope"
  | "audio"
  | "supervisor";

const FAMILIES: [string, Family][] = [
  ["turn.", "turn"],
  ["supervisor.", "supervisor"],
  ["tool", "tool"],
  ["confirm.", "consent"],
  ["stage.", "stage"],
  ["state", "state"],
  ["session.", "envelope"],
  ["tts.", "audio"],
  ["stt.", "audio"],
  ["audio.", "audio"],
];

interface EventRowProps {
  event: SessionEvent;
  /** The grant that paid for this event, when this event is the call it authorised. */
  authorised: ConsentLink | null;
}

export function EventRow({ event, authorised }: EventRowProps) {
  return (
    <tr className={`log__row log__row--${familyOf(event.kind)}`}>
      <td className="num faint">{event.seq}</td>
      <td className="num faint">{event.t_ms}</td>
      <td className="log__kind mono">{event.kind}</td>
      <td className="log__detail">
        <Detail event={event} authorised={authorised} />
      </td>
    </tr>
  );
}

/** Which rule colour this kind carries down the left of the log. */
export function familyOf(kind: string): Family {
  for (const [prefix, family] of FAMILIES) {
    if (kind.startsWith(prefix)) return family;
  }
  return "state";
}

function Detail({ event, authorised }: EventRowProps) {
  const { kind, payload } = event;

  if (kind === "session.start") return <Start payload={payload} />;
  if (kind === "session.end") return <End payload={payload} />;
  if (kind === "state") return <Transition payload={payload} verb="→" />;
  if (kind === "stage.handoff") return <Transition payload={payload} verb="handoff →" />;
  if (kind === "stage.enter") return <Chip label="stage" value={text(payload["stage"]) ?? "?"} />;
  if (kind.startsWith("turn.")) return <Turn event={event} />;
  if (kind === "tts.word") return <Karaoke payload={payload} />;
  if (kind === "stt.final" || kind === "stt.interim") return <Said payload={payload} />;
  if (kind === "tool.call") return <ToolCall payload={payload} authorised={authorised} />;
  if (kind === "tool.result") return <ToolResult payload={payload} />;
  if (kind.startsWith("confirm.")) return <Confirm kind={kind} payload={payload} />;
  if (kind === "tools.executed") return <Chip label="tools" value={String(payload["count"])} />;
  if (kind === "audio.start") return <Chip label="recording" value={String(payload["path"])} />;
  if (kind.startsWith("supervisor.")) return <Supervision payload={payload} />;
  return <Raw payload={payload} />;
}

/** A second human on the line: who, with which powers, and whether the caller could see them. */
function Supervision({ payload }: { payload: Record<string, unknown> }) {
  return (
    <span className="detail">
      <Chip label="who" value={text(payload["identity"]) ?? "?"} />
      <Chip label="as" value={text(payload["capability"]) ?? "?"} />
      <Chip label="hidden" value={payload["hidden"] === false ? "no" : "yes"} />
    </span>
  );
}


/* ── the envelope ────────────────────────────────────────────────────────── */

function Start({ payload }: { payload: Record<string, unknown> }) {
  const sip = asRecord(payload["sip"]);
  const caller = sip ? text(sip["sip.phoneNumber"]) : null;
  return (
    <span className="detail">
      <Chip label="project" value={`${payload["tenant"]}/${payload["project"]}`} />
      <Chip label="channel" value={String(payload["channel"])} />
      {payload["git_sha"] != null && <Chip label="build" value={String(payload["git_sha"])} />}
      {caller && <Chip label="from" value={caller} accent />}
    </span>
  );
}

function End({ payload }: { payload: Record<string, unknown> }) {
  const cost = asRecord(payload["cost"]);
  const eur = cost && typeof cost["eur"] === "number" ? cost["eur"] : null;
  const outcome = text(payload["outcome"]) ?? "none";
  return (
    <span className="detail">
      <span className={`outcome outcome--${outcome}`}>{outcome}</span>
      {payload["reason"] != null && <Chip label="reason" value={String(payload["reason"])} />}
      {eur !== null && <Chip label="cost" value={`${eur.toFixed(4)} €`} />}
    </span>
  );
}

function Transition({ payload, verb }: { payload: Record<string, unknown>; verb: string }) {
  return (
    <span className="detail mono dim">
      {String(payload["from"])} <span className="faint">{verb}</span> {String(payload["to"])}
    </span>
  );
}

/* ── what was said ───────────────────────────────────────────────────────── */

function Turn({ event }: { event: SessionEvent }) {
  const who = event.kind === "turn.user" ? "caller" : "agent";
  return (
    <div className="turn">
      <p className={`turn__text turn__text--${who}`}>{String(event.payload["text"] ?? "")}</p>
      <span className="detail">
        {turnChips(event).map((chip) => (
          <Chip key={chip.label} label={chip.label} value={chip.value} />
        ))}
      </span>
    </div>
  );
}

function Said({ payload }: { payload: Record<string, unknown> }) {
  return (
    <span className="detail">
      <span className="dim">{String(payload["text"] ?? "")}</span>
      {payload["language"] != null && <Chip label="lang" value={String(payload["language"])} />}
    </span>
  );
}

/** The TTS words as one spoken phrase, with each word's offset kept on hover. */
function Karaoke({ payload }: { payload: Record<string, unknown> }) {
  const words = Array.isArray(payload["words"]) ? payload["words"] : [];
  const spoken = words.map((word) => asRecord(word)).filter((word) => word !== null);
  const phrase = spoken.map((word) => String(word["w"] ?? "")).join(" ");
  const timings = spoken
    .map((word) => `${word["w"]}@${Number(word["t1"] ?? 0).toFixed(2)}`)
    .join(" ");
  return (
    <span className="detail" title={timings}>
      <span className="karaoke">{phrase}</span>
      <span className="chip__key">{spoken.length}w</span>
    </span>
  );
}

/* ── the tools, and what paid for them ───────────────────────────────────── */

function ToolCall({
  payload,
  authorised,
}: {
  payload: Record<string, unknown>;
  authorised: ConsentLink | null;
}) {
  const effect = text(payload["side_effect"]) ?? "read";
  const args = asRecord(payload["args"]) ?? {};
  return (
    <div className="detail detail--stack">
      <span className="detail">
        <span className="tool mono">{String(payload["tool"])}</span>
        <span className={`effect effect--${effect}`}>{effect}</span>
        {authorised?.granted != null && (
          <span className="consent__link">authorised by seq {authorised.granted}</span>
        )}
      </span>
      {Object.keys(args).length > 0 && (
        <span className="args mono">
          {Object.entries(args).map(([key, value]) => (
            <span key={key} className="args__pair">
              <span className="chip__key">{key}</span>
              {stringify(value)}
            </span>
          ))}
        </span>
      )}
    </div>
  );
}

function ToolResult({ payload }: { payload: Record<string, unknown> }) {
  return (
    <span className="detail">
      <span className="tool mono">{String(payload["tool"])}</span>
      <Chip label="shape" value={String(payload["shape"] ?? "—")} />
      <span className="faint">the log records the shape, never the contents</span>
    </span>
  );
}

function Confirm({ kind, payload }: { kind: string; payload: Record<string, unknown> }) {
  const question = text(payload["question"]);
  return (
    <div className="detail detail--stack">
      <span className="detail">
        <span className="consent__verb">{kind.replace("confirm.", "")}</span>
        <span className="tool mono">{String(payload["tool"])}</span>
        <span className="chip__key mono">{String(payload["audience"] ?? "")}</span>
      </span>
      {question && <p className="consent__question">“{question}”</p>}
    </div>
  );
}

function Raw({ payload }: { payload: Record<string, unknown> }) {
  return <span className="mono faint">{JSON.stringify(payload)}</span>;
}

/* ── the smallest piece ──────────────────────────────────────────────────── */

function Chip({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <span className={`chip${accent ? " chip--accent" : ""}`}>
      <span className="chip__key">{label}</span>
      {value}
    </span>
  );
}

function stringify(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}
