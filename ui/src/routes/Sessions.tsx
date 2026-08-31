/* Sessions — every conversation one project has had, newest first, in one dense table.
 *
 * The table is the whole screen on purpose: eight columns an operator scans
 * down, no cards, no charts. A row is a link into the log that produced it.
 */

import { Link, useLoaderData, type LoaderFunctionArgs } from "react-router";

import { EmptyState } from "../components/EmptyState";
import { ScoreChip } from "../components/ScoreChip";
import { listSessions, type SessionLine } from "../lib/api";
import { sectionPath } from "../lib/nav";
import { euros, mediumOf, startedAt } from "../lib/sessions";

const LIMIT = 200;

interface SessionsData {
  tenant: string;
  project: string;
  rows: SessionLine[];
  error: string | null;
}

/** Load one project's call log; a dead control plane leaves the screen empty, not broken. */
export async function sessionsLoader({ params }: LoaderFunctionArgs): Promise<SessionsData> {
  const tenant = params["tenant"] ?? "";
  const project = params["project"] ?? "";
  try {
    const rows = await listSessions({ tenant, project, limit: LIMIT });
    return { tenant, project, rows, error: null };
  } catch (cause) {
    const error = cause instanceof Error ? cause.message : String(cause);
    return { tenant, project, rows: [], error };
  }
}

export function Sessions() {
  const { tenant, project, rows, error } = useLoaderData() as SessionsData;

  return (
    <div className="page page--wide">
      <header className="page__head">
        <div className="page__eyebrow">
          {tenant} / {project}
        </div>
        <h1 className="page__title">Sessions</h1>
        <p className="page__lede">
          Every conversation this project has had, newest first — phone calls included. A row opens
          the session&apos;s append-only log: one line per fact, numbered by{" "}
          <code className="mono">seq</code>, with the per-turn STT / LLM / TTS breakdown and the
          consent proof beside it. The <strong>score</strong> column is the call judging itself:
          four checks decided by code and at most one Haiku call, written into the same log as{" "}
          <code className="mono">session.score</code> within a minute of the caller hanging up.
        </p>
      </header>

      {rows.length > 0 && (
        <section className="section">
          <div className="table-wrap">
            <table className="table table--calls">
              <thead>
                <tr>
                  <th>session</th>
                  <th>project</th>
                  <th>channel</th>
                  <th>started</th>
                  <th>outcome</th>
                  <th>score</th>
                  <th className="num">turns</th>
                  <th className="num">events</th>
                  <th className="num">cost</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <Row key={row.id} tenant={tenant} project={project} row={row} />
                ))}
              </tbody>
            </table>
          </div>
          <p className="note">
            {rows.length} session{rows.length === 1 ? "" : "s"} · the same rows{" "}
            <code className="mono">python -m convo sessions list</code> prints
          </p>
        </section>
      )}

      {rows.length === 0 && (
        <section className="section">
          <EmptyState
            title={error ? "The control plane did not answer" : "No sessions recorded yet"}
            milestone="ms-9"
            command={`curl -s 'localhost:8090/sessions?tenant=${tenant}&project=${project}&limit=20'`}
          >
            <p>
              {error ? (
                <>
                  <code className="mono">GET /sessions</code> failed with{" "}
                  <code className="mono">{error}</code>. Start it with{" "}
                  <code className="mono">uv run uvicorn api:app --port 8090</code>.
                </>
              ) : (
                <>
                  The log is append-only and written during the call, so a session appears here the
                  moment one starts — from the browser, from{" "}
                  <code className="mono">python worker.py console</code>, or from the telephone.
                </>
              )}
            </p>
          </EmptyState>
        </section>
      )}
    </div>
  );
}

/** One call: identity, medium, envelope, and the two numbers that price it. */
function Row({ tenant, project, row }: { tenant: string; project: string; row: SessionLine }) {
  const medium = mediumOf(row);
  const live = row.ended_at === null;

  return (
    <tr>
      <td className="id">
        <Link to={`${sectionPath(tenant, project, "sessions")}/${row.id}`} className="link">
          {row.id}
        </Link>
      </td>
      <td className="dim mono">{row.project}</td>
      <td>
        <span className={`medium medium--${medium}`}>{medium}</span>
        {row.phone && <span className="medium__number mono">{row.phone}</span>}
      </td>
      <td className="mono dim">{startedAt(row.started_at)}</td>
      <td>
        {live ? (
          <span className="outcome outcome--live">running</span>
        ) : (
          <span className={`outcome outcome--${row.outcome ?? "none"}`}>{row.outcome ?? "—"}</span>
        )}
      </td>
      <td>
        <ScoreChip score={row.score} running={live} />
      </td>
      <td className="num dim">{row.turns}</td>
      <td className="num faint">{row.events}</td>
      <td className="num dim">{euros(row.cost_eur)}</td>
    </tr>
  );
}
