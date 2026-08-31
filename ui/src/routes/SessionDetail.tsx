/* One session, read as its log: the envelope, the latency, the consent, then every fact in seq.
 *
 * The order is an auditor's: what this call was, how fast it was, what it was
 * allowed to do, and only then the rows that prove all three. Everything above
 * the table is derived from the table — nothing on this screen comes from
 * anywhere the CLI could not reach.
 */

import { Link, useLoaderData, type LoaderFunctionArgs } from "react-router";

import { ConsentProof } from "../components/ConsentProof";
import { EmptyState } from "../components/EmptyState";
import { EventRow } from "../components/EventRow";
import { LatencyStrip } from "../components/LatencyStrip";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { getSession, recordingUrl, type SessionView } from "../lib/api";
import {
  authorisedBy,
  consentLinks,
  costLines,
  duration,
  endReason,
  euros,
  latencyStrip,
  mediumOf,
  sipOf,
  stagesOf,
  startedAt,
} from "../lib/sessions";

interface DetailData {
  tenant: string;
  id: string;
  view: SessionView | null;
  error: string | null;
}

/** Load one session in full — the row, the report and every event in seq order. */
export async function sessionDetailLoader({ params }: LoaderFunctionArgs): Promise<DetailData> {
  const tenant = params["tenant"] ?? "";
  const id = params["id"] ?? "";
  try {
    return { tenant, id, view: await getSession(id), error: null };
  } catch (cause) {
    return { tenant, id, view: null, error: cause instanceof Error ? cause.message : String(cause) };
  }
}

export function SessionDetail() {
  const { tenant, id, view, error } = useLoaderData() as DetailData;

  if (!view) {
    return (
      <div className="page">
        <Head tenant={tenant} id={id} />
        <section className="section">
          <EmptyState title="That session did not load" command={`curl -s localhost:8090/sessions/${id}`}>
            <p>
              <code className="mono">{error ?? "unknown error"}</code>
            </p>
          </EmptyState>
        </section>
      </div>
    );
  }

  const events = view.events_log;
  const links = consentLinks(events);
  const sip = sipOf(events);
  const stages = stagesOf(view);

  return (
    <div className="page page--wide">
      <Head tenant={tenant} id={id} />

      <section className="section">
        <div className="facts">
          <Fact label="project" value={`${view.tenant}/${view.project}`} />
          <Fact label="channel" value={mediumOf(view)} accent={sip !== null} />
          <Fact label="started" value={startedAt(view.started_at)} />
          <Fact label="duration" value={duration(view) ?? "running"} />
          <Fact label="outcome" value={view.outcome ?? "running"} />
          <Fact label="cost" value={euros(view.cost_eur)} />
          <Fact label="score" value={view.score ? view.score.score.toFixed(2) : "—"} />
          <Fact label="turns" value={String(view.turns)} />
          <Fact label="events" value={String(view.events)} />
          {endReason(events) && <Fact label="reason" value={endReason(events) ?? ""} />}
          {stages.length > 0 && <Fact label="stages" value={stages.join(" → ")} />}
        </div>
      </section>

      {view.audio && (
        <section className="section">
          <h2 className="section__title">Listen to this call</h2>
          <audio className="player" controls preload="none" src={recordingUrl(id)}>
            <a href={recordingUrl(id)}>Download the recording</a>
          </audio>
          <p className="note">
            Stereo: the caller on the left channel, the agent on the right, on one absolute
            timeline whose sample zero is the <code className="mono">audio.start</code> row below.
            The file never leaves the box except through this authenticated route — it is not in
            git and it is not a static mount. A supervisor who took the line is audible to the
            caller but <strong>not</strong> in this recording: the tap hears the caller and the
            agent, and that is the one thing it does not hear.
          </p>
        </section>
      )}

      <section className="section">
        <h2 className="section__title">Latency across this call</h2>
        <LatencyStrip stats={latencyStrip(events)} />
        <p className="note">
          Median and max over the turns that carried each leg — the same seconds{" "}
          <code className="mono">python -m convo sessions show {id}</code> prints per turn, for the
          four legs it prints. <code className="mono">tts_node_ttfb</code> is in the payload and not
          on that line, so compare the first four and read the last off the rows below.
        </p>
      </section>

      <section className="section">
        <h2 className="section__title">Consent proof</h2>
        <ConsentProof links={links} />
      </section>

      <section className="section">
        <h2 className="section__title">Score</h2>
        <ScoreBreakdown score={view.score} />
        <p className="note">
          Written into the log itself as <code className="mono">session.score</code>, with the next{" "}
          <code className="mono">seq</code> — the same row{" "}
          <code className="mono">python -m convo sessions show {id}</code> prints at the bottom of
          the table below.
        </p>
      </section>

      {costLines(events).length > 0 && (
        <section className="section">
          <h2 className="section__title">Cost by model</h2>
          <div className="panel">
            <div className="panel__body">
              <table className="kv">
                <tbody>
                  {costLines(events).map((line) => (
                    <tr key={`${line.provider}/${line.model}`}>
                      <td className="kv__key">
                        {line.provider} · {line.model}
                      </td>
                      <td className="kv__val">{euros(line.eur)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {sip && (
        <section className="section">
          <details className="fold">
            <summary className="fold__summary">
              <span className="fold__title">SIP</span>
              <span className="mono dim">
                {sip.caller ?? "unknown caller"} → {sip.dialled ?? "unknown trunk"}
              </span>
              <span className="faint">{sip.attributes.length} attributes</span>
            </summary>
            <div className="fold__body">
              <table className="kv">
                <tbody>
                  {sip.attributes.map(([key, value]) => (
                    <tr key={key}>
                      <td className="kv__key">{key}</td>
                      <td className="kv__val">{value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </section>
      )}

      <section className="section">
        <h2 className="section__title">The log</h2>
        <div className="table-wrap table-wrap--tall">
          <table className="table table--log">
            <thead>
              <tr>
                <th className="num">seq</th>
                <th className="num">t_ms</th>
                <th>kind</th>
                <th>payload</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <EventRow key={event.seq} event={event} authorised={authorisedBy(links, event.seq)} />
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          {events.length} events, append-only, numbered from sample zero. Live ≡ stored: the tail
          streams over SSE while the call is up and reads identically afterwards.
        </p>
      </section>
    </div>
  );
}

/** The page's title strip: where you are, and which session you are reading. */
function Head({ tenant, id }: { tenant: string; id: string }) {
  return (
    <header className="page__head">
      <div className="page__eyebrow">
        <Link to={`/t/${tenant}/sessions`}>{tenant} / sessions</Link>
      </div>
      <h1 className="page__title page__title--mono">{id}</h1>
    </header>
  );
}

/** One labelled number in the envelope row. */
function Fact({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`fact${accent ? " fact--accent" : ""}`}>
      <div className="fact__key">{label}</div>
      <div className="fact__val">{value}</div>
    </div>
  );
}
