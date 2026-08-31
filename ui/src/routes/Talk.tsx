/* Talk — the screen where a human reaches the agent, by any of the three doors.
 *
 * The platform is one process runtime behind three channels: WebRTC voice
 * from this browser, text chat from this browser, and an inbound phone call
 * over the SIP trunk. This screen refuses to treat them as three features.
 * Whichever door the caller used, the transcript renders the same way —
 * interim grey settling to final, the agent filling word by word at the pace
 * of its own audio — and the same log streams down the right-hand side.
 *
 * Chat is text ONLY: it never asks for a microphone and shows no audio
 * control, because the session it opens has no audio tracks at all
 * (`RoomOptions(audio_input=False, audio_output=False)`), so there is no STT
 * and no TTS to put a knob on.
 *
 * A phone call is watched, not joined: POST /observe mints a hidden,
 * publish-nothing ticket, and the listen-in audio starts MUTED — a supervisor
 * reads a call by default and only chooses to hear it.
 */

import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";

import { LiveCalls } from "../components/LiveCalls";
import { Timeline } from "../components/Timeline";
import { Transcript } from "../components/Transcript";
import type { LiveCall } from "../lib/api";
import { sectionPath } from "../lib/nav";
import { useRoom, type Live, type Mode } from "../lib/useRoom";
import { useTimeline } from "../lib/useTimeline";

import { useShellData } from "./Shell";

export function Talk() {
  const { tenant = "", project = "" } = useParams();
  const { tenants } = useShellData();
  const known = tenants.find((row) => row.tenant === tenant)?.projects.find((p) => p.id === project);

  const live = useRoom(tenant, project);
  const log = useTimeline(live.phase === "live" ? live.room : null);
  const [caller, setCaller] = useState<string | null>(null);

  const watch = (call: LiveCall) => {
    setCaller(call.phone ?? "web");
    void live.open("observe", call.room);
  };

  return (
    <div className="page page--wide">
      <header className="page__head">
        <div className="page__eyebrow">
          {tenant} / {project}
        </div>
        <h1 className="page__title">{known?.name ?? project}</h1>
        <p className="page__lede">
          One runtime, three ways in — the microphone in this tab, a text session with no audio at
          all, or the SIP trunk, if this project has a number of its own (
          <Link className="accent" to={sectionPath(tenant, project, "pipeline")}>
            Pipeline
          </Link>{" "}
          names it, or says there is none). The transcript and the log below do not know which one
          you used.
        </p>
      </header>

      <section className="section">
        <h2 className="section__title">Conversation</h2>
        <div className="talk">
          <div className="talk__main">
            <Controls live={live} caller={caller} />
            <Transcript lines={live.lines} state={live.state} empty={hint(live.phase, live.mode)} />
            {live.mode === "chat" && <Composer live={live} />}
            {live.error && <p className="note note--warn">{live.error}</p>}
          </div>
          <Timeline log={log} tenant={tenant} project={project} />
        </div>
      </section>

      <LiveCalls onObserve={watch} watching={live.mode === "observe" ? live.room : null} />
    </div>
  );
}

/** The bar above the transcript: which door, whether it is open, and what the agent is doing. */
function Controls({ live, caller }: { live: Live; caller: string | null }) {
  const busy = live.phase === "connecting";
  const on = live.phase === "live";

  return (
    <div className="talk__bar">
      <div className="talk__doors">
        <Door mode="voice" live={live} label="Voice" />
        <Door mode="chat" live={live} label="Chat" />
      </div>

      <div className="talk__status">
        {live.mode === "observe" && on && (
          <span className="badge badge--live">observing {caller ?? "a call"}</span>
        )}
        {live.state && <span className="state">{live.state}</span>}
        {busy && <span className="badge">connecting…</span>}
        {live.phase === "ended" && <span className="badge">ended</span>}

        {on && live.mode === "observe" && (
          <button type="button" className="button" onClick={() => live.listen(!live.audible)}>
            {live.audible ? "mute listen-in" : "listen in"}
          </button>
        )}
        {on && (
          <button type="button" className="button button--stop" onClick={() => void live.close()}>
            {live.mode === "observe" ? "stop watching" : "hang up"}
          </button>
        )}
      </div>
    </div>
  );
}

function Door({ mode, live, label }: { mode: Mode; live: Live; label: string }) {
  const here = live.mode === mode && live.phase !== "idle" && live.phase !== "ended";

  return (
    <button
      type="button"
      className={here ? "door door--on" : "door"}
      disabled={live.phase === "connecting"}
      onClick={() => void live.open(mode)}
    >
      {label}
    </button>
  );
}

/** The chat box. It exists in chat mode and nowhere else — a voice call has no text input. */
function Composer({ live }: { live: Live }) {
  const [draft, setDraft] = useState("");

  const send = (event: FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    void live.say(text);
  };

  return (
    <form className="composer" onSubmit={send}>
      <input
        className="composer__input"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="say something"
        disabled={live.phase !== "live"}
        autoFocus
      />
      <button type="submit" className="button" disabled={live.phase !== "live" || !draft.trim()}>
        send
      </button>
    </form>
  );
}

/** What the empty transcript should say, which is never "no data". */
function hint(phase: Live["phase"], mode: Live["mode"]): string {
  if (phase === "connecting") return "joining the room…";
  if (phase === "failed") return "the room did not open";
  if (phase === "live" && mode === "voice") return "listening — say something";
  if (phase === "live" && mode === "chat") return "type below; the agent answers on lk.transcription";
  if (phase === "live") return "watching this call — nothing has been said since you joined";
  if (phase === "ended") return "the call ended";
  return "pick a door, or click observe on a call below";
}
