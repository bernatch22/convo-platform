/* Talk — the screen where a human reaches the agent, by any of the three doors.
 *
 * The platform is one runtime behind three channels: WebRTC voice from this
 * browser, web chat from this browser, and an inbound phone call over the SIP
 * trunk. Same tenant, same project, same event log — only the transport
 * differs, and this screen has to say that before it can do anything.
 */

import { useParams } from "react-router";

import { EmptyState } from "../components/EmptyState";
import { LiveCalls } from "../components/LiveCalls";

import { useShellData } from "./Shell";

/** The public number of the Twilio Elastic SIP trunk pointed at this deploy. */
const PHONE_NUMBER = "+1 417 674 3169";

export function Talk() {
  const { tenant = "", project = "" } = useParams();
  const { tenants } = useShellData();
  const known = tenants.find((row) => row.tenant === tenant)?.projects.find((p) => p.id === project);

  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">{tenant}</div>
        <h1 className="page__title">{known?.name ?? project}</h1>
        <p className="page__lede">
          One process runtime, three ways in. Whichever door a caller uses, the same project
          answers, the same tools run under the same guard, and the same append-only log is
          written.
        </p>
      </header>

      <section className="section">
        <h2 className="section__title">Channels</h2>
        <div className="grid grid--3">
          <Channel
            name="Voice"
            kind="webrtc"
            note="Microphone in this tab, over LiveKit. Soniox transcribes, Haiku answers, ElevenLabs speaks — interim words appear as they are heard."
            address="livekit · publish + subscribe"
          />
          <Channel
            name="Chat"
            kind="text"
            note="No audio tracks at all: the session opens with audio_input and audio_output off. You type on lk.chat, the agent streams back on lk.transcription."
            address="livekit · data only"
          />
          <Channel
            name="Phone"
            kind="pstn"
            note="Inbound over the Twilio Elastic SIP trunk into livekit-sip. The number decides the tenant and project, so no browser is involved — the call appears below and POST /observe joins it hidden, publishing nothing."
            address={PHONE_NUMBER}
            live
          />
        </div>
      </section>

      <LiveCalls />

      <section className="section">
        <EmptyState
          title="No session open"
          milestone="ms-9"
          card="the Talk cards"
          command={`curl -s localhost:8090/token -H 'content-type: application/json' -d '{"tenant":"${tenant}","project":"${project}","channel":"chat"}'`}
        >
          <p>
            This shell is the frame only. Connecting the microphone, the chat box and the live
            transcript is the next card of ms-9: raw <code className="mono">livekit-client</code>,
            interim → final transcription, karaoke at audio pace, and the turn/tool timeline down
            the right-hand side — the same three for a phone call joined as an observer.
          </p>
          <p>
            The control plane already mints the ticket, so the door is open — the command below
            returns the room and the JWT this screen will join.
          </p>
        </EmptyState>
      </section>
    </div>
  );
}

interface ChannelProps {
  name: string;
  kind: string;
  note: string;
  address: string;
  live?: boolean;
}

function Channel({ name, kind, note, address, live = false }: ChannelProps) {
  return (
    <article className="channel">
      <div className="channel__top">
        <span className="channel__name">{name}</span>
        <span className="badge">{kind}</span>
      </div>
      <p className="channel__note">{note}</p>
      <div className={live ? "channel__addr channel__addr--live" : "channel__addr"}>{address}</div>
    </article>
  );
}
