/* The two verbs that change a live call: whisper to the agent, or take the line off it.
 *
 * Every verb here is an RPC to the agent's own participant, and the method
 * name is the audit kind — `supervisor.steer`, `supervisor.takeover`,
 * `supervisor.release`. Nothing is sent as a `{"role": "supervisor"}` claim in
 * a body: the agent gates on the `caller_identity` the SFU read off the JWT,
 * so a refusal here is a signature failing, not a field being wrong.
 *
 * The grant is the whole design and this desk is honest about it. A `listen`
 * ticket may not send data, so it CANNOT whisper — asking to whisper re-mints
 * the ticket with the `whisper` grant, still hidden and still silent, for the
 * SAME `sup:<uid>`, which is why LiveKit upgrades the participant already in
 * the room instead of admitting a second ghost. Taking the line re-mints again
 * with `takeover`: a real microphone, and a participant the caller can see.
 * Each escalation is a reconnect, and the transcript on screen survives it.
 *
 * The order in `take` matters and is not cosmetic: the ticket first (there is
 * no microphone to publish without it), the microphone second, the verb last —
 * so by the time the agent goes quiet the human is already audible. `hand`
 * runs it backwards for the same reason.
 */

import { useState, type FormEvent } from "react";

import type { SupervisorCapability } from "../lib/api";
import type { Live } from "../lib/useRoom";
import { RELEASE, STEER, TAKEOVER } from "../lib/verbs";

/** The whisper box and the takeover switch, for one call this desk is already monitoring. */
export function WhisperDesk({ live, me }: { live: Live; me: string }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const holding = live.capability === "takeover";

  const run = async (what: string, job: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setSaid(null);
    try {
      await job();
      setSaid(what);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const escalate = async (capability: SupervisorCapability) => {
    if (live.capability === capability) return;
    await live.open("supervise", live.room ?? undefined, { capability, userId: me });
  };

  const whisper = (event: FormEvent) => {
    event.preventDefault();
    const text = note.trim();
    if (!text) return;
    void run("whispered — the caller heard nothing", async () => {
      await escalate(holding ? "takeover" : "whisper");
      const answered = await live.verb(STEER, { text, mode: "inject_and_speak" });
      setNote("");
      if (answered.queued) setSaid("queued — it lands on the agent's next turn");
    });
  };

  const take = () =>
    run("you have the line — the agent is muted", async () => {
      await escalate("takeover");
      await live.mic(true);
      await live.verb(TAKEOVER, {});
    });

  const hand = () =>
    run("handed back — the agent resumes knowing what it missed", async () => {
      await live.verb(RELEASE, {});
      await live.mic(false);
      await escalate("listen");
    });

  return (
    <div className="section">
      <form className="composer" onSubmit={whisper}>
        <input
          className="composer__input"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="whisper to the agent — the caller never hears this"
          disabled={busy || live.phase !== "live"}
        />
        <button type="submit" className="button" disabled={busy || !note.trim()}>
          whisper
        </button>
        {holding ? (
          <button type="button" className="button button--stop" disabled={busy} onClick={hand}>
            hand the line back
          </button>
        ) : (
          <button type="button" className="button" disabled={busy} onClick={take}>
            take the line
          </button>
        )}
      </form>

      <p className="note">
        <Grant capability={live.capability} holding={holding} />
        {said && <span className="badge badge--live">{said}</span>}
        {error && <span className="badge badge--warn">{error}</span>}
      </p>
    </div>
  );
}

/** What this desk's current ticket allows, in the SFU's terms and not in ours. */
function Grant({
  capability,
  holding,
}: {
  capability: SupervisorCapability | null;
  holding: boolean;
}) {
  if (holding) {
    return (
      <>
        <code className="mono">takeover</code> — your microphone is live and the caller can see
        you. The agent answers nothing until you hand the line back.{" "}
      </>
    );
  }
  return (
    <>
      <code className="mono">{capability ?? "listen"}</code> — hidden and silent. A whisper
      upgrades the ticket to <code className="mono">whisper</code> for the same{" "}
      <code className="mono">sup:</code> identity; it is still not a voice in the room.{" "}
    </>
  );
}
