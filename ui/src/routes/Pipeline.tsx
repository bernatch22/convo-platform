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
          three fields an operator may change without a deploy.
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
          shown from the invariants in CLAUDE.md — the live values and the medians come from GET
          /pipeline
        </p>
      </section>

      <section className="section">
        <EmptyState
          title="Nothing is controllable from here yet"
          milestone="ms-9"
          card="tk-667be6"
          command={`curl -s localhost:8090/pipeline/${tenant}/<project>`}
        >
          <p>
            <code className="mono">GET /pipeline/{"{tenant}"}/{"{project}"}</code> will report the
            three legs as they are actually configured plus the measured ttft / e2e / eot medians,
            and <code className="mono">PUT</code> will let an operator change voice, TTS model and
            greeting for the next session — applied by{" "}
            <code className="mono">core.router.resolve</code>, so no deploy and no restart.
          </p>
          <p>
            The provider rules still hold at the door: a PUT of a forbidden TTS model comes back
            422 naming the rule it broke.
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
        <span className="badge badge--accent">{role}</span>
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
