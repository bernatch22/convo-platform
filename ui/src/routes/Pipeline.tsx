/* Pipeline — see the three providers a project runs on, and change what is changeable.
 *
 * One GET answers the whole screen: the STT / LLM / TTS legs as the NEXT
 * session will run them (overrides already applied by the control plane), the
 * medians its stored calls measured, and the three fields a supervisor may
 * set. The project lives in the query string, so a screen is shareable and
 * switching project is a navigation, not a store write.
 */

import { useState } from "react";
import { Link, redirect, useLoaderData, useParams, type LoaderFunctionArgs } from "react-router";

import { PipelineControls } from "../components/PipelineControls";
import { LlmLeg, SttLeg, TtsLeg } from "../components/PipelineLegs";
import { Waterfall } from "../components/Waterfall";
import { ApiError, getPipeline, listTenants, type PipelineSnapshot } from "../lib/api";

import { useShellData } from "./Shell";

/** What this screen renders: one project's snapshot, or the refusal that replaced it. */
export interface PipelineData {
  tenant: string;
  project: string | null;
  snapshot: PipelineSnapshot | null;
  error: string | null;
}

/** Read one project's pipeline; with no `?project=` in the URL, redirect to the tenant's first. */
export async function pipelineLoader({
  params,
  request,
}: LoaderFunctionArgs): Promise<PipelineData> {
  const tenant = params.tenant ?? "";
  const wanted = new URL(request.url).searchParams.get("project");

  if (!wanted) {
    const first = (await listTenants()).find((row) => row.tenant === tenant)?.projects[0];
    if (!first) {
      return { tenant, project: null, snapshot: null, error: `${tenant} has no projects` };
    }
    throw redirect(`/t/${tenant}/pipeline?project=${encodeURIComponent(first.id)}`);
  }

  try {
    return { tenant, project: wanted, snapshot: await getPipeline(tenant, wanted), error: null };
  } catch (cause) {
    const error = cause instanceof ApiError ? cause.detail : String(cause);
    return { tenant, project: wanted, snapshot: null, error };
  }
}

export function Pipeline() {
  const { tenant = "" } = useParams();
  const data = useLoaderData() as PipelineData;
  const { tenants } = useShellData();
  const projects = tenants.find((row) => row.tenant === tenant)?.projects ?? [];

  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">{tenant} · pipeline</div>
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
          {projects.map((project) => (
            <Link
              key={project.id}
              to={`/t/${tenant}/pipeline?project=${encodeURIComponent(project.id)}`}
              className={project.id === data.project ? "tabs__tab is-active" : "tabs__tab"}
            >
              {project.id}
            </Link>
          ))}
        </nav>
      )}

      {data.snapshot ? (
        <Loaded key={data.project} snapshot={data.snapshot} />
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
        <h2 className="section__title">Anatomy of a turn</h2>
        <Waterfall
          medians={shown.latency.medians}
          sessions={shown.latency.sessions}
          turns={shown.latency.turns}
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
              <td className="mono">{row.value || "(empty)"}</td>
              <td className="mono dim">{new Date(row.updated_at * 1000).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
