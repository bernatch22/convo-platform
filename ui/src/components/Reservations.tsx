/* The reservations themselves: who, when, with whom, and how each one stands.
 *
 * This is the first thing on the Board because it is the first thing an
 * operator asks, and it is the one table on this console that does NOT come
 * out of the append-only log. The log's summaries are PII-filtered by design —
 * the platform is not where a patient's name is kept — so the names here are
 * read from the customer's own system, through the tenant's adapter, which is
 * exactly where they have always lived and exactly who they are for.
 *
 * One table, one system: the Board draws this component once per system that
 * offers a record view, so a shop's orders and a shop's incidents are two
 * tables with two shapes and never one table with a mixed vocabulary.
 *
 * Nothing in this file knows what a reservation is called. The business names
 * its records, heads its own columns and picks its own word for a state; the
 * only thing this component decides is how loudly to draw a row, and even that
 * is the adapter's `tone` and not a guess made here. So a clinic gets an
 * agenda, a shop gets its orders, and a tenant whose systems offer no such
 * view gets a sentence saying so rather than an empty agenda that never was.
 */

import { Link } from "react-router";

import type { BusinessRecord, RecordLabels, RecordTable } from "../lib/api";
import { sectionPath } from "../lib/nav";
import { startedAt } from "../lib/sessions";

interface ReservationsProps {
  view: RecordTable | null;
  error: string | null;
  tenant: string;
  project: string;
}

/** The business table, or the honest reason there is none. */
export function Reservations({ view, error, tenant, project }: ReservationsProps) {
  if (error !== null) {
    return (
      <p className="note">
        <code className="mono">GET /reservations</code> failed with{" "}
        <code className="mono">{error}</code> — the control plane could not reach this
        project&apos;s systems, so this screen shows no records rather than stale ones.
      </p>
    );
  }

  if (view === null || view.shape === null) {
    return (
      <p className="note">
        None of <strong>{tenant}</strong>&apos;s systems offers a record view for{" "}
        <strong>{project}</strong>. An adapter opts in by declaring the{" "}
        <code className="mono">list_records</code> capability — see{" "}
        <code className="mono">core/adapters/base.py</code>. Nothing is invented here in the
        meantime.
      </p>
    );
  }

  if (view.rows.length === 0) {
    return (
      <p className="note">
        <strong>{view.systems.join(", ") || "the system"}</strong> answered with no{" "}
        {view.shape} at all. That is the business&apos;s own answer and this screen repeats it.
      </p>
    );
  }

  return (
    <>
      <div className="table-wrap">
        <table className="table table--agenda">
          <thead>
            <tr>
              <th>{view.labels.who ?? "who"}</th>
              {view.labels.when && <th>{view.labels.when}</th>}
              {view.labels.handled_by && <th>{view.labels.handled_by}</th>}
              <th>state</th>
              {view.labels.contact && <th>{view.labels.contact}</th>}
              {view.labels.detail && <th>{view.labels.detail}</th>}
              <th>call</th>
            </tr>
          </thead>
          <tbody>
            {view.rows.map((row) => (
              <Row key={row.id} row={row} labels={view.labels} tenant={tenant} project={project} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">
        {view.rows.length} {view.shape} · read from{" "}
        <code className="mono">{view.systems.join(", ")}</code>, the tenant&apos;s own system, and
        joined to the call log on the identifier the log carries verbatim. A row with no call
        behind it was already on the book before we rang.
      </p>
    </>
  );
}

interface RowProps {
  row: BusinessRecord;
  labels: RecordLabels;
  tenant: string;
  project: string;
}

/** One record: the person, the moment, who is on it, how it stands, and the call it came from. */
function Row({ row, labels, tenant, project }: RowProps) {
  return (
    <tr className={row.tone === "gone" ? "agenda__row is-gone" : "agenda__row"}>
      <td className="agenda__who">{row.who || <span className="faint">—</span>}</td>
      {labels.when && <td className="mono dim">{moment(row.when)}</td>}
      {labels.handled_by && <td>{row.handled_by ?? <span className="faint">—</span>}</td>}
      <td>
        <span className={`state state--${row.tone}`} title={callNote(row)}>
          {row.state}
        </span>
      </td>
      {labels.contact && <td className="mono dim">{row.contact ?? "—"}</td>}
      {labels.detail && <td className="did">{row.detail ?? <span className="faint">—</span>}</td>}
      <td className="id">
        {row.session ? (
          <Link className="link" to={`${sectionPath(tenant, project, "sessions")}/${row.session}`}>
            {row.session}
          </Link>
        ) : (
          <span className="faint">—</span>
        )}
      </td>
    </tr>
  );
}

/** `2026-09-04T10:00` reads as a day and an hour; a plain date stays a date. */
function moment(when: string | null): string {
  if (!when) return "—";
  const [day, clock] = when.split("T");
  const shown = new Date(`${day}T00:00:00`);
  if (Number.isNaN(shown.getTime())) return when;
  const label = shown.toLocaleDateString(undefined, { month: "short", day: "2-digit" });
  return clock ? `${label} ${clock.slice(0, 5)}` : label;
}

/** What the log knows about this row, for the state chip's tooltip. */
function callNote(row: BusinessRecord): string {
  if (!row.verb) return "no call in this window touched this record";
  const yes = row.confirmed ? "the caller's yes was on record" : "no confirmation preceded it";
  return `${row.verb} at ${startedAt(row.at ?? 0)} — ${yes}`;
}
