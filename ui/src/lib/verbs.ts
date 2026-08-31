/* The supervision verbs, as a browser sends them: one RPC to the agent, named after the log line.
 *
 * `supervisor.steer` is both the RPC method the agent registers and the kind
 * that lands in the caller's event log. One string, so a screen, a handler and
 * an audit row cannot drift apart — and so reading the log tells you exactly
 * which call was made.
 *
 * Nothing here claims a role. The agent gates on the `caller_identity` the SFU
 * reads off the JWT it verified, so what makes a whisper land is the signature
 * on the ticket this browser joined with, not a field in the payload. A ticket
 * without the grant fails at the SFU; a ticket with the grant but the wrong
 * identity fails at the agent; both come back here as a thrown `RpcError`,
 * which is why a refused verb is shown and never swallowed.
 */

import { ParticipantKind, type Participant, type Room } from "livekit-client";

/** Whisper a note into the agent's context; the caller hears nothing. */
export const STEER = "supervisor.steer";

/** Mute the agent: it stops speaking and answers no turn until the line is handed back. */
export const TAKEOVER = "supervisor.takeover";

/** Give the line back, with the human's interval summarised into the agent's context. */
export const RELEASE = "supervisor.release";

/** Move the call to a phone: `cold` REFERs the caller away, `warm` bridges a briefed colleague. */
export const TRANSFER = "supervisor.transfer";

/** True when this participant is the agent — `kind`, never a guess at the identity string. */
export function isAgent(participant: Participant): boolean {
  return participant.kind === ParticipantKind.AGENT;
}

/** Aim one verb at this room's agent and return what it answered.
 *
 * Throws when there is no agent in the room (a call that already ended) and
 * re-throws the agent's own `RpcError` for anything it refused.
 */
export async function aim(
  room: Room,
  kind: string,
  body: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
  const agent = [...room.remoteParticipants.values()].find(isAgent);
  if (!agent) throw new Error("no agent in this call to steer");
  const answer = await room.localParticipant.performRpc({
    destinationIdentity: agent.identity,
    method: kind,
    payload: JSON.stringify(body),
  });
  return JSON.parse(answer) as Record<string, unknown>;
}
