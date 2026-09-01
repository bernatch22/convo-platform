/* Board — the reservations first, and what the platform did to make them second.
 *
 * This screen used to open with counters, and counters were the wrong answer to
 * the question an operator actually asks. They wanted the AGENDA: who is
 * coming, when, with whom, and whether that booking still stands. So the table
 * of real records leads, the tallies are demoted to one strip of numbers under
 * it, and the transaction log — which is still the evidence, and still the only
 * thing an auditor should read — sits at the bottom where it belongs.
 *
 * Two reads, two sources, and the difference is the point:
 *
 *   GET /reservations  the customer's own system, through its adapter. Names,
 *                      because a booking system is where a name belongs.
 *   GET /outcomes      our append-only log. Counts, and summaries the PII mask
 *                      scrubbed on the way in, because that is where it belongs.
 *
 * Neither can be derived from the other, and the rows are joined on the one
 * thing that crosses the mask: the business's own identifier.
 *
 * The window is in the URL (`?days=30`), like every other piece of state in
 * this console: a board is a thing you send somebody, so the link has to carry
 * what it was showing.
 */

import { Link, useLoaderData, type LoaderFunctionArgs } from "react-router";

import { EmptyState } from "../components/EmptyState";
import { OutcomeBars } from "../components/OutcomeBars";
import { Reservations } from "../components/Reservations";
import {
  ApiError,
  getOutcomes,
  getReservations,
  type BusinessView,
  type OutcomeBoard,
  type OutcomeRow,
  type RecordTable,
} from "../lib/api";
import { sectionPath } from "../lib/nav";
import { startedAt } from "../lib/sessions";

/** Every table this project has, in the tenant's own order — or one that explains the absence.
 *
 * A business may keep its records in more than one system, and those are not
 * rows of one table: a shop's orders and a shop's incidents have different
 * columns and different words for a state. The Board draws one section each.
 * When there is no view at all — or the read failed — a single null table is
 * still returned, because `Reservations` is what says so in words.
 */
function tablesOf(records: BusinessView | null): (RecordTable | null)[] {
  if (records === null) return [null];
  return records.views.length > 0 ? records.views : [records];
}

/** The windows the header offers. Any `?days=` in range works; these are the ones with a button. */
const WINDOWS = [7, 14, 30, 90] as const;

const DEFAULT_DAYS = 14;
const ROWS = 200;

/** What this screen renders: one project's records, its transactions, and any refusal. */
export interface BoardData {
  tenant: string;
  project: string;
  days: number;
  records: BusinessView | null;
  recordsError: string | null;
  board: OutcomeBoard | null;
  error: string | null;
}

/** Read the business system and the log over the same window; either may fail on its own. */
export async function boardLoader({ params, request }: LoaderFunctionArgs): Promise<BoardData> {
  const tenant = params["tenant"] ?? "";
  const project = params["project"] ?? "";
  const days = windowOf(new URL(request.url).searchParams.get("days"));

  const [records, board] = await Promise.all([
    settle(() => getReservations({ tenant, project, days, limit: ROWS })),
    settle(() => getOutcomes({ tenant, project, days, limit: ROWS })),
  ]);

  return {
    tenant,
    project,
    days,
    records: records.value,
    recordsError: records.error,
    board: board.value,
    error: board.error,
  };
}

export function Board() {
  const { tenant, project, days, records, recordsError, board, error } =
    useLoaderData() as BoardData;
  const empty = board === null || board.totals.transactions === 0;

  return (
    <div className="page page--wide">
      <header className="page__head">
        <div className="page__eyebrow">
          {tenant} / {project}
        </div>
        <h1 className="page__title">Board</h1>
        <p className="page__lede">
          The <strong>records themselves</strong>, read off this tenant&apos;s own systems — who,
          when, with whom, and how each one stands. Names live there and not in our log, whose
          summaries are PII-filtered on the way in; what the platform DID to produce them is the
          strip and the table below, counted off that log, where one{" "}
          <code className="mono">tool.call</code> declared{" "}
          <code className="mono">irreversible</code> is one transaction. The two are joined on the
          business&apos;s own identifier — the one thing that crosses the mask.
        </p>
        <Windows tenant={tenant} project={project} days={days} />
      </header>

      {tablesOf(records).map((table, index) => (
        <section className="section" key={table?.shape ?? `records-${index}`}>
          <h2 className="section__title">{table?.shape ?? "records"}</h2>
          <Reservations view={table} error={recordsError} tenant={tenant} project={project} />
        </section>
      ))}

      {board !== null && !empty && (
        <>
          <section className="section">
            <Strip board={board} />
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
            milestone="ms-19"
            command={`curl -s 'localhost:8090/reservations?tenant=${tenant}&project=${project}'`}
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
                  <code className="mono">irreversible</code>, so nothing above has a call behind it
                  yet. Book, move or cancel something —{" "}
                  <code className="mono">python worker.py console</code> is enough — and both the
                  record and the transaction land here the moment the tool returns.
                </>
              )}
            </p>
          </EmptyState>
        </section>
      )}
    </div>
  );
}

/** The counters, demoted: one line of numbers under the records they explain. */
function Strip({ board }: { board: OutcomeBoard }) {
  return (
    <div className="strip">
      {board.verbs.map((tally) => (
        <div key={tally.verb} className="strip__cell">
          <span className="strip__value num">{tally.count}</span>
          <span className="strip__name mono">{tally.verb}</span>
          {tally.failed > 0 && <span className="strip__bad">{tally.failed} failed</span>}
        </div>
      ))}
      <div className="strip__cell strip__cell--quiet">
        <span className="strip__value num">{board.totals.sessions}</span>
        <span className="strip__name mono">calls</span>
        <span className="faint">
          {board.totals.confirmed} of {board.totals.transactions} confirmed in {board.days} days
        </span>
      </div>
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

/** One read, and the sentence it failed with — so a dead half of the screen never empties the other. */
async function settle<T>(read: () => Promise<T>): Promise<{ value: T | null; error: string | null }> {
  try {
    return { value: await read(), error: null };
  } catch (cause) {
    return { value: null, error: cause instanceof ApiError ? cause.detail : String(cause) };
  }
}

/** The window the URL asked for, clamped to what the control plane will serve. */
function windowOf(raw: string | null): number {
  const asked = Number(raw);
  if (!Number.isFinite(asked) || asked < 1) return DEFAULT_DAYS;
  return Math.min(90, Math.round(asked));
}
