/* What was said, as the wire says it — the one model behind every live transcript.
 *
 * Both sides of a conversation arrive on the same topic (`lk.transcription`)
 * and differ only in cadence, verified against livekit-agents 1.7's
 * `room_io/_output.py`:
 *
 *   user (STT)  `is_delta_stream=False` — one whole stream per update. Every
 *               interim opens a writer, writes the full text, closes; the
 *               final is yet another stream carrying the SAME `lk.segment_id`
 *               with `lk.transcription_final: "true"`.
 *   agent (TTS) `is_delta_stream=True` — ONE stream per segment, written in
 *               deltas at the pace the voice is synthesised, and closed with
 *               the final flag in the trailer.
 *
 * Which means one rule serves both: a segment's text is the text accumulated
 * by the most recent stream carrying its id. The user's later stream replaces
 * the interim; the agent's single stream grows word by word — that growth IS
 * the karaoke, and it needs no timer because the audio set its pace.
 *
 * `reader.info.attributes` only tells the truth about `final` AFTER the
 * iteration ends: the trailer overwrites it on close
 * (`IncomingDataStreamManager.ts:401`), so during the loop it always says
 * "false".
 */

/** Who a line belongs to. The agent is a participant of kind AGENT; everyone else is a caller. */
export type Speaker = "user" | "agent";

/** One transcription segment: grey while `final` is false, solid once it settles. */
export interface Line {
  id: string;
  speaker: Speaker;
  text: string;
  final: boolean;
}

/** The agent's own word for what it is doing, off the `lk.agent.state` attribute. */
export type AgentState = "idle" | "initializing" | "listening" | "thinking" | "speaking";

export const SEGMENT_ID = "lk.segment_id";
export const TRANSCRIPTION_FINAL = "lk.transcription_final";
export const AGENT_STATE = "lk.agent.state";

/** Add or replace one segment, keeping first-arrival order — never reorder a transcript. */
export function upsert(lines: Line[], line: Line): Line[] {
  const at = lines.findIndex((row) => row.id === line.id);
  if (at === -1) return [...lines, line];
  const next = lines.slice();
  next[at] = line;
  return next;
}

/** The words of a line, keeping the spaces, so the renderer can animate each arrival once. */
export function words(text: string): string[] {
  return text.split(/(\s+)/).filter((part) => part.length > 0);
}

/** The state a `lk.agent.state` attribute names, or null when it is absent or unknown. */
export function agentState(value: string | undefined): AgentState | null {
  const known: AgentState[] = ["idle", "initializing", "listening", "thinking", "speaking"];
  return known.find((state) => state === value) ?? null;
}
