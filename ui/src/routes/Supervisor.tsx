/* Supervisor — the monitor: a human hears and reads a live call the caller never dialled them into.
 *
 * One click on a row in the strip does three things, in this order and no
 * other. It mints a short-lived `listen` ticket at POST /supervise — hidden,
 * subscribe-only, expiring in fifteen minutes. It joins the room with it, and
 * subscribes to both audio tracks MUTED, because a supervisor reads a call by
 * default and only then chooses to hear it. Then it tells the control plane it
 * is through the door, and the control plane asks the SFU whether that is true
 * before writing `supervisor.join` into the caller's own log.
 *
 * That last step is what the "hidden" badge on this screen means. It is not
 * our word for it: it is `permission.hidden` read back off the SFU's copy of
 * the token, so the screen is showing the supervisor the server's own answer
 * to "can the person on the phone see me". Measured on this box: they cannot —
 * a hidden participant fires no ParticipantConnected on any other client.
 *
 * The transcript is the SAME component the Talk screen uses, fed by the same
 * `lk.transcription` streams, for a phone call this browser has no other
 * relationship with. One runtime, one log, one screen — from the other side.
 */

import { useEffect, useMemo, useState } from "react";

import { LiveCalls } from "../components/LiveCalls";
import { Timeline } from "../components/Timeline";
import { Transcript } from "../components/Transcript";
import { WhisperDesk } from "../components/WhisperDesk";
import { superviseEntered, type LiveCall, type SupervisorPresence } from "../lib/api";
import { useRoom, type Live } from "../lib/useRoom";
import { useTimeline } from "../lib/useTimeline";

/** The call being monitored, as the strip described it — the log knows nothing of rooms. */
interface Watched {
  caller: string;
  tenant: string;
  project: string;
}

export function Supervisor() {
  const live = useRoom("", "");
  const log = useTimeline(live.phase === "live" ? live.room : null);
  const entry = useEntry(live);
  const [watched, setWatched] = useState<Watched | null>(null);
  // One desk, one `sup:<uid>`, for as long as this tab is open: escalating a
  // ticket has to UPGRADE the participant already in the room, and LiveKit
  // decides that by identity. A fresh uid per click would be a second person.
  const me = useMemo(() => Math.random().toString(36).slice(2, 10), []);

  const monitor = (call: LiveCall) => {
    setWatched({
      caller: call.phone ?? "web",
      tenant: call.tenant ?? "",
      project: call.project ?? "",
    });
    void live.open("supervise", call.room, { capability: "listen", userId: me });
  };

  return (
    <div className="page page--wide">
      <header className="page__head">
        <div className="page__eyebrow">fleet</div>
        <h1 className="page__title">Supervisor</h1>
        <p className="page__lede">
          Every call in progress across every tenant, phone calls included. A supervisor enters one
          of them with a short-lived ticket from <code className="mono">POST /supervise</code>: the
          identity is always <code className="mono">sup:&lt;uid&gt;</code>, and the capability
          inside the token — not a control on this screen — is what separates listening from taking
          the line.
        </p>
      </header>

      <LiveCalls
        onObserve={monitor}
        watching={live.mode === "supervise" ? live.room : null}
        verb="listen"
      />

      {live.mode === "supervise" && live.phase !== "idle" && (
        <section className="section">
          <h2 className="section__title">Monitoring</h2>
          <div className="talk">
            <div className="talk__main">
              <MonitorBar live={live} watched={watched} entry={entry} />
              <Transcript lines={live.lines} state={live.state} empty={hint(live.phase)} />
              {live.phase === "live" && <WhisperDesk live={live} me={me} />}
              {live.error && <p className="note note--warn">{live.error}</p>}
            </div>
            <Timeline
              log={log}
              tenant={watched?.tenant ?? ""}
              project={watched?.project ?? ""}
            />
          </div>
        </section>
      )}

      <section className="section">
        <h2 className="section__title">What a ticket allows</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>capability</th>
                <th>in the room</th>
                <th>logged as</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="mono">listen</td>
                <td>hidden, subscribe-only — the caller is never told anybody joined</td>
                <td className="mono">supervisor.join</td>
              </tr>
              <tr>
                <td className="mono">whisper</td>
                <td>still hidden and still silent, but may send the agent text over RPC</td>
                <td className="mono">supervisor.steer</td>
              </tr>
              <tr>
                <td className="mono">takeover</td>
                <td>a real microphone, and a participant the caller can see</td>
                <td className="mono">supervisor.takeover</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="note">
          Each verb is appended to the caller&apos;s own session log with its own{" "}
          <code className="mono">seq</code>, so one call stays one story.
        </p>
      </section>
    </div>
  );
}

/** The bar above the transcript: who is being monitored, what the SFU says, and the two verbs. */
function MonitorBar({ live, watched, entry }: { live: Live; watched: Watched | null; entry: Entry }) {
  const on = live.phase === "live";

  return (
    <div className="talk__bar">
      <div className="talk__status">
        <span className="badge badge--live">monitoring {watched?.caller ?? "a call"}</span>
        {live.identity && <span className="badge">{live.identity}</span>}
        <Hidden entry={entry} />
        {live.state && <span className="state">{live.state}</span>}
        {live.phase === "connecting" && <span className="badge">joining…</span>}
        {live.phase === "ended" && <span className="badge">left</span>}
      </div>

      <div className="talk__status">
        {on && (
          <button type="button" className="button" onClick={() => live.listen(!live.audible)}>
            {live.audible ? "mute" : "listen in"}
          </button>
        )}
        {on && (
          <button type="button" className="button button--stop" onClick={() => void live.close()}>
            stop monitoring
          </button>
        )}
      </div>
    </div>
  );
}

/** The SFU's own answer to "can the caller see me", which is the only one worth showing. */
function Hidden({ entry }: { entry: Entry }) {
  if (entry.error) return <span className="badge badge--warn">unconfirmed</span>;
  if (!entry.presence) return <span className="badge">confirming…</span>;
  if (!entry.presence.hidden) return <span className="badge badge--warn">visible to the caller</span>;
  return (
    <span className="badge badge--live">
      hidden · {entry.presence.announced ? "supervisor.join logged" : "no agent to log it"}
    </span>
  );
}

/** What the control plane answered when told this supervisor is in the room. */
interface Entry {
  presence: SupervisorPresence | null;
  error: string | null;
}

/** Announce the arrival once per join, and keep what the SFU said about it. */
function useEntry(live: Live): Entry {
  const { phase, mode, room, identity } = live;
  const [presence, setPresence] = useState<SupervisorPresence | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPresence(null);
    setError(null);
    if (phase !== "live" || mode !== "supervise" || !room || !identity) return;
    let alive = true;
    superviseEntered(room, identity)
      .then((seen) => alive && setPresence(seen))
      .catch((cause) => alive && setError(cause instanceof Error ? cause.message : String(cause)));
    return () => {
      alive = false;
    };
  }, [phase, mode, room, identity]);

  return { presence, error };
}

/** What the empty transcript should say, which is never "no data". */
function hint(phase: Live["phase"]): string {
  if (phase === "connecting") return "joining the room…";
  if (phase === "failed") return "the room did not open";
  if (phase === "ended") return "you left the call";
  return "on the line — nothing has been said since you joined";
}
