/* Pipeline — see the three providers a project runs on, and change what is changeable. */

import { useParams } from "react-router";

import { EmptyState } from "../components/EmptyState";

import { useShellData } from "./Shell";

export function Pipeline() {
  const { tenant = "" } = useParams();
  const { tenants } = useShellData();
  const projects = tenants.find((row) => row.tenant === tenant)?.projects ?? [];

  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">{tenant}</div>
        <h1 className="page__title">Pipeline</h1>
        <p className="page__lede">
          The three legs of a voice turn as data, not as prose: what hears, what decides, what
          speaks — with the medians measured over this project&apos;s stored sessions, and the
          three fields a supervisor may change without a deploy.
        </p>
      </header>

      <section className="section">
        <h2 className="section__title">Legs</h2>
        <div className="grid grid--3">
          <Leg
            role="hears"
            provider="Soniox"
            rows={[
              ["model", "stt-rt-v5"],
              ["hints", "es · en"],
              ["endpointing", "level 2 · 0.3"],
              ["max delay", "1000 ms"],
            ]}
          />
          <Leg
            role="decides"
            provider="Anthropic"
            rows={[
              ["model", "claude-haiku-4-5"],
              ["caching", "ephemeral"],
              ["cache floor", "4096 tok"],
              ["preemptive", "retries 1"],
            ]}
          />
          <Leg
            role="speaks"
            provider="ElevenLabs"
            rows={[
              ["model", "eleven_v3_conversational"],
              ["alignment", "sync"],
              ["voice", projects[0]?.voice ?? "—"],
              ["projects", String(projects.length)],
            ]}
          />
        </div>
        <p className="note">
          the platform&apos;s invariants — the live snapshot and the medians come from GET /pipeline
        </p>
      </section>

      <section className="section">
        <EmptyState
          title="Reading the real snapshot is the next card"
          milestone="ms-9"
          card="the pipeline card"
          command={`curl -s localhost:8090/pipeline/${tenant}/${projects[0]?.id ?? "<project>"}`}
        >
          <p>
            <code className="mono">GET /pipeline/{"{tenant}"}/{"{project}"}</code> is merged: the
            three legs as the NEXT session will run them, the overrides already applied, and the
            medians (<code className="mono">transcription_delay</code>,{" "}
            <code className="mono">end_of_turn_delay</code>, <code className="mono">llm_node_ttft</code>
            , <code className="mono">tts_node_ttfb</code>, <code className="mono">e2e_latency</code>)
            — null, never zero, when nothing measured them.
          </p>
          <p>
            <code className="mono">PUT</code> takes voice, tts_model and greeting and returns the
            changed snapshot, so no refetch. A model the platform refuses to run comes back 422
            naming the rule it broke.
          </p>
        </EmptyState>
      </section>
    </div>
  );
}

interface LegProps {
  role: string;
  provider: string;
  rows: [string, string][];
}

function Leg({ role, provider, rows }: LegProps) {
  return (
    <article className="panel">
      <div className="panel__head">
        <span className="panel__title">{provider}</span>
        <span className="badge">{role}</span>
      </div>
      <div className="panel__body">
        <table className="kv">
          <tbody>
            {rows.map(([key, value]) => (
              <tr key={key}>
                <td className="kv__key">{key}</td>
                <td className="kv__val">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}
