/* The other half of a live call: what the runtime wrote down while it was happening.
 *
 * The browser knows the room; the log knows the session. Nothing in the ticket
 * joins the two, and for a phone call there is no ticket at all — so the join
 * is GET /live-calls, which is the one place that sees both the SFU's rooms
 * and the sessions still running. Once it names a session id, the SSE tail at
 * /sessions/{id}/live delivers every append in seq order, and a turn's
 * latencies arrive with the turn instead of after the call.
 *
 * The same two steps serve a WebRTC session and an inbound phone call, which
 * is the whole point: one runtime, one log, one screen.
 */

import { useEffect, useState } from "react";

import { listLiveCalls, watchSession, type SessionEvent } from "./api";

const FIND_MS = 2000;

/** Where the log is: still looking for it, streaming, finished, or not being watched at all. */
export type LogStatus = "off" | "finding" | "live" | "ended";

/** One session's log as it is written, plus how the search for it went. */
export interface Timeline {
  session: string | null;
  events: SessionEvent[];
  status: LogStatus;
  outcome: string | null;
}

/** Follow the log of whatever session is running in `room`; idle when there is none. */
export function useTimeline(room: string | null): Timeline {
  const session = useSessionOf(room);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [status, setStatus] = useState<LogStatus>("off");
  const [outcome, setOutcome] = useState<string | null>(null);

  useEffect(() => {
    setEvents([]);
    setOutcome(null);
    if (!session) {
      setStatus(room ? "finding" : "off");
      return;
    }
    setStatus("live");
    return watchSession(session, 0, (frame) => {
      if (frame.type === "append") {
        setEvents((seen) => [...seen, frame.event]);
      } else if (frame.type === "end") {
        setOutcome(frame.outcome);
        setStatus("ended");
      }
    });
  }, [room, session]);

  return { session, events, status, outcome };
}

/** Ask the SFU which stored session is logging this room, until it knows. */
function useSessionOf(room: string | null): string | null {
  const [session, setSession] = useState<string | null>(null);

  useEffect(() => {
    setSession(null);
    if (!room) return;
    let alive = true;
    let timer = 0;
    const look = async () => {
      const found = await sessionOf(room);
      if (!alive) return;
      if (found) setSession(found);
      else timer = window.setTimeout(() => void look(), FIND_MS);
    };
    void look();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [room]);

  return session;
}

/** The session id /live-calls matched to this room, or null while nobody has matched it yet. */
async function sessionOf(room: string): Promise<string | null> {
  try {
    const calls = await listLiveCalls();
    return calls.find((call) => call.room === room)?.session_id ?? null;
  } catch {
    return null; // the SFU is down or the room is gone; the caller keeps asking
  }
}
