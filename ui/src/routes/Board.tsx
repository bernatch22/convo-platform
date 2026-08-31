/* Board — what the platform DID to the business: created, moved, cancelled, on one screen.
 *
 * Sessions answers "who called". This answers the question an operator asks at
 * the end of a week: how many appointments were booked, moved and cancelled,
 * and can I see the call behind each one. Both come out of the same
 * append-only log — there is no second table and no counter kept beside the
 * write, so a number here and the log it was counted from cannot drift.
 *
 * Nothing on this screen knows what a verb is called. The counters, the bars
 * and the rows are all drawn from whatever `GET /outcomes` returned, and a
 * project that declares a new irreversible tool tomorrow appears here the
 * first time it runs, with no code changed in this file.
 *
 * The window is in the URL (`?days=30`), like every other piece of state in
 * this console: a board is a thing you send somebody, so the link has to carry
 * what it was showing.
 */

import { Link, useLoaderData, type LoaderFunctionArgs } from "react-router";

import { EmptyState } from "../components/EmptyState";
import { OutcomeBars } from "../components/OutcomeBars";
import { ApiError, getOutcomes, type OutcomeBoard, type OutcomeRow } from "../lib/api";
import { sectionPath } from "../lib/nav";
import { startedAt } from "../lib/sessions";

/** The windows the header offers. Any `?days=` in range works; these are the ones with a button. */
const WINDOWS = [7, 14, 30, 90] as const;

const DEFAULT_DAYS = 14;
const ROWS = 200;

/** What this screen renders: one project's transactions, or the refusal that replaced them. */
export interface BoardData {
  tenant: string;
  project: string;
  days: number;
  board: OutcomeBoard | null;
  error: string | null;
}

/** Read one project's outcomes over the window the URL names; a dead API empties the screen. */
export async function boardLoader({ params, request }: LoaderFunctionArgs): Promise<BoardData> {
  const tenant = params["tenant"] ?? "";
  const project = params["project"] ?? "";
  const days = windowOf(new URL(request.url).searchParams.get("days"));

  try {
    const board = await getOutcomes({ tenant, project, days, limit: ROWS });
    return { tenant, project, days, board, error: null };
  } catch (cause) {
    const error = cause instanceof ApiError ? cause.detail : String(cause);
    return { tenant, project, days, board: null, error };
  }
}

export function Board() {
  const { tenant, project, days, board, error } = useLoaderData() as BoardData;
  const empty = board === null || board.totals.transactions === 0;

  return (
    <div className="page page--wide">
      <header className="page__head">
        <div className="page__eyebrow">
          {tenant} / {project}
        </div>
        <h1 className="page__title">Board</h1>
        <p className="page__lede">
          Every <strong>irreversible</strong> thing this project did to the business, counted off
          the same append-only log the sessions are read from — one{" "}
          <code className="mono">tool.call</code> whose{" "}
          <code className="mono">side_effect</code> is <code className="mono">irreversible</code> is
          one transaction, and the <strong>yes</strong> column is the{" "}
          <code className="mono">confirm.granted</code> that authorised it. Nothing is counted
          twice and nothing is stored twice: there is no rollup table, the log is the table.
        </p>
        <Windows tenant={tenant} project={project} days={days} />
      </header>

      {board !== null && !empty && (
        <>
          <section className="section">
            <div className="counters">
              {board.verbs.map((tally) => (
                <div key={tally.verb} className="counter">
                  <div className="counter__value num">{tally.count}</div>
                  <div className="counter__name mono">{tally.verb}</div>
                  <div className="counter__foot">
                    <span>{tally.confirmed} confirmed</span>
                    {tally.failed > 0 && <span className="counter__bad">{tally.failed} failed</span>}
                    {tally.pending > 0 && <span className="faint">{tally.pending} pending</span>}
                  </div>
                </div>
              ))}
              <div className="counter counter--quiet">
                <div className="counter__value num">{board.totals.sessions}</div>
                <div className="counter__name mono">calls</div>
                <div className="counter__foot">
                  <span className="faint">
                    {board.totals.transactions} transaction
                    {board.totals.transactions === 1 ? "" : "s"} in {board.days} days
                  </span>
                </div>
              </div>
            </div>
          </section>

          <section className="section">
            <h2 className="section__title">By day</h2>
            <OutcomeBars series={board.series} verbs={board.verbs} />
          </section>

          <section className="section">
            <h2 className="section__title">Transactions</h2>
            <div className="table-wrap">
              <table className="table table--board">
                <thead>
                  <tr>
                    <th>when</th>
                    <th>verb</th>
                    <th>yes</th>
                    <th>result</th>
                    <th>what it did</th>
                    <th>session</th>
                  </tr>
                </thead>
                <tbody>
                  {board.rows.map((row) => (
                    <Row key={`${row.session}-${row.seq}`} row={row} />
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note">
              {board.rows.length} transaction{board.rows.length === 1 ? "" : "s"} · the{" "}
              <strong>what it did</strong> column is the line the tool&apos;s own{" "}
              <code className="mono">result_summary</code> rendered and the session&apos;s PII mask
              scrubbed, reused verbatim — a tool that declares no renderer has no line, and this
              screen invents none.
            </p>
          </section>
        </>
      )}

      {empty && (
        <section className="section">
          <EmptyState
            title={error ? "The control plane did not answer" : "Nothing irreversible yet"}
            milestone="ms-18"
            command={`curl -s 'localhost:8090/outcomes?tenant=${tenant}&project=${project}&days=${days}'`}
          >
            <p>
              {error ? (
                <>
                  <code className="mono">GET /outcomes</code> failed with{" "}
                  <code className="mono">{error}</code>. Start it with{" "}
                  <code className="mono">uv run uvicorn api:app --port 8090</code>.
                </>
              ) : (
                <>
                  No call in the last {days} days ran a tool declared{" "}
                  <code className="mono">irreversible</code>. Book, move or cancel something —{" "}
                  <code className="mono">python worker.py console</code> is enough — and the
                  transaction lands here the moment the tool returns, because it is the same log
                  line the call already wrote.
                </>
              )}
            </p>
          </EmptyState>
        </section>
      )}
    </div>
  );
}

/** The window picker: four links, because the window belongs in the URL and not in a state hook. */
function Windows({ tenant, project, days }: { tenant: string; project: string; days: number }) {
  const base = sectionPath(tenant, project, "board");

  return (
    <div className="windows">
      {WINDOWS.map((span) => (
        <Link
          key={span}
          to={`${base}?days=${span}`}
          className={span === days ? "windows__pick is-active" : "windows__pick"}
        >
          {span}d
        </Link>
      ))}
    </div>
  );
}

/** One transaction: when, what, whether the caller said yes, and the call it happened in. */
function Row({ row }: { row: OutcomeRow }) {
  return (
    <tr>
      <td className="mono dim">{startedAt(row.at)}</td>
      <td className="mono">{row.verb}</td>
      <td>
        <span
          className={row.confirmed ? "granted granted--yes" : "granted granted--none"}
          title={
            row.confirmed
              ? "a confirm.granted for this tool stood unspent before the call"
              : "no granted confirmation preceded this irreversible call"
          }
        >
          {row.confirmed ? "yes" : "—"}
        </span>
      </td>
      <td>
        <span className={`outcome outcome--${row.status}`}>{row.status}</span>
      </td>
      <td className="did">
        {row.summary ?? <span className="faint">no summary declared</span>}
      </td>
      <td className="id">
        <Link
          to={`${sectionPath(row.tenant, row.project, "sessions")}/${row.session}`}
          className="link"
        >
          {row.session}
        </Link>
      </td>
    </tr>
  );
}

/** The window the URL asked for, clamped to what the control plane will serve. */
function windowOf(raw: string | null): number {
  const asked = Number(raw);
  if (!Number.isFinite(asked) || asked < 1) return DEFAULT_DAYS;
  return Math.min(90, Math.round(asked));
}
