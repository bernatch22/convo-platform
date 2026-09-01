/* Pipeline — see the three providers a project runs on, and change what is changeable.
 *
 * One GET answers the whole screen: the STT / LLM / TTS legs as the NEXT
 * session will run them (overrides already applied by the control plane), the
 * medians its stored calls measured, and the three fields a supervisor may
 * set. The project is in the path — `/t/<tenant>/<project>/pipeline` — so this
 * screen never guesses which project it is configuring, and switching project
 * is a navigation, not a store write.
 */

import { useState } from "react";
import { Link, useLoaderData, type LoaderFunctionArgs } from "react-router";

import { PhoneLines } from "../components/PhoneLines";
import { PipelineControls } from "../components/PipelineControls";
import { LlmLeg, SttLeg, TtsLeg } from "../components/PipelineLegs";
import { Waterfall } from "../components/Waterfall";
import { ApiError, getPipeline, type PipelineSnapshot } from "../lib/api";
import { sectionPath } from "../lib/nav";
import { voiceName } from "../lib/voices";

import { useShellData } from "./Shell";

/** What this screen renders: one project's snapshot, or the refusal that replaced it. */
export interface PipelineData {
  tenant: string;
  project: string;
  snapshot: PipelineSnapshot | null;
  error: string | null;
}

/** Read the pipeline of the project the path names — there is nothing left to default. */
export async function pipelineLoader({ params }: LoaderFunctionArgs): Promise<PipelineData> {
  const tenant = params["tenant"] ?? "";
  const project = params["project"] ?? "";

  try {
    return { tenant, project, snapshot: await getPipeline(tenant, project), error: null };
  } catch (cause) {
    const error = cause instanceof ApiError ? cause.detail : String(cause);
    return { tenant, project, snapshot: null, error };
  }
}

export function Pipeline() {
  const data = useLoaderData() as PipelineData;
  const { tenant, project } = data;
  const { tenants } = useShellData();
  const projects = tenants.find((row) => row.tenant === tenant)?.projects ?? [];

  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">
          {tenant} / {project} · pipeline
        </div>
        <h1 className="page__title">{data.snapshot?.name ?? "Pipeline"}</h1>
        <p className="page__lede">
          The three legs of a voice turn as data, not as prose: what hears, what decides, what
          speaks — every value read from the platform&apos;s own configuration with this
          project&apos;s overrides already applied, so this screen cannot show a pipeline the next
          call will not run.
        </p>
      </header>

      {projects.length > 1 && (
        <nav className="tabs" aria-label="Projects">
          {projects.map((row) => (
            <Link
              key={row.id}
              to={sectionPath(tenant, row.id, "pipeline")}
              className={row.id === project ? "tabs__tab is-active" : "tabs__tab"}
            >
              {row.id}
            </Link>
          ))}
        </nav>
      )}

      {data.snapshot ? (
        <Loaded key={project} snapshot={data.snapshot} />
      ) : (
        <p className="ctl__error">{data.error}</p>
      )}
    </div>
  );
}

function Loaded({ snapshot }: { snapshot: PipelineSnapshot }) {
  const [shown, setShown] = useState(snapshot);

  return (
    <>
      <section className="section">
        <h2 className="section__title">Providers</h2>
        <div className="grid grid--3">
          <SttLeg stt={shown.stt} />
          <LlmLeg llm={shown.llm} />
          <TtsLeg tts={shown.tts} />
        </div>
      </section>

      <section className="section">
        <h2 className="section__title">Phone</h2>
        <p className="note">
          The number is a route, not a property of this project: one row of the control
          plane&apos;s <code className="mono">routes</code> table, keyed by the fleet and the
          number the caller dialled, and the same row{" "}
          <code className="mono">core/router.py</code> reads to decide who answers. A project with
          no row is not reachable by phone at all — the other two doors, voice in the browser and
          chat, are open to every project regardless.
        </p>
        <PhoneLines phone={shown.phone} />
      </section>

      <section className="section">
        <h2 className="section__title">Anatomy of a turn</h2>
        <Waterfall
          medians={shown.latency.medians}
          sessions={shown.latency.sessions}
          turns={shown.latency.turns}
          project={`${shown.tenant}/${shown.project}`}
        />
      </section>

      <section className="section">
        <h2 className="section__title">Control</h2>
        <PipelineControls snapshot={shown} onSaved={setShown} />
        <Overrides snapshot={shown} />
      </section>
    </>
  );
}

/** A stored value as a human reads it: a voice id leads with the account name it belongs to. */
function overrideValue(field: string, value: string): string {
  if (!value) return "(empty)";
  const named = field === "voice" ? voiceName(value) : null;
  return named ? `${named} · ${value}` : value;
}

function Overrides({ snapshot }: { snapshot: PipelineSnapshot }) {
  if (snapshot.overrides.length === 0) {
    return (
      <p className="note">
        nothing overridden — this project runs exactly what git deployed. The console may set{" "}
        <code className="mono">{snapshot.overridable.join(", ")}</code>.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>field</th>
            <th>value</th>
            <th>changed</th>
          </tr>
        </thead>
        <tbody>
          {snapshot.overrides.map((row) => (
            <tr key={row.field}>
              <td className="mono">{row.field}</td>
              <td className="mono">{overrideValue(row.field, row.value)}</td>
              <td className="mono dim">{new Date(row.updated_at * 1000).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
