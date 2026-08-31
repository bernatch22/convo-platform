/* Sessions — the call log for one tenant. The columns are the API's; the rows arrive next card. */

import { useParams } from "react-router";

import { EmptyState } from "../components/EmptyState";

/** The columns of GET /sessions, in the order an operator scans them. */
const COLUMNS = [
  { key: "id", num: false },
  { key: "project", num: false },
  { key: "channel", num: false },
  { key: "started_at", num: false },
  { key: "outcome", num: false },
  { key: "turns", num: true },
  { key: "events", num: true },
  { key: "cost_eur", num: true },
];

export function Sessions() {
  const { tenant = "" } = useParams();

  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">{tenant}</div>
        <h1 className="page__title">Sessions</h1>
        <p className="page__lede">
          Every conversation this tenant has had, newest first — phone calls included. A row opens
          the session&apos;s append-only log: one line per fact, numbered by{" "}
          <code className="mono">seq</code>, with the per-turn STT / LLM / TTS breakdown and the
          consent proof beside it.
        </p>
      </header>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column.key} className={column.num ? "num" : ""}>
                  {column.key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={COLUMNS.length} className="faint mono">
                no rows loaded
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section className="section">
        <EmptyState
          title="The table has its columns, not its loader"
          milestone="ms-9"
          card="the sessions card"
          command={`curl -s 'localhost:8090/sessions?tenant=${tenant}&limit=20'`}
        >
          <p>
            <code className="mono">GET /sessions</code> is merged and answering — these are its
            fields, verbatim. What this screen still needs is the route loader that calls it and
            the row rendering, which is a card of its own so this seam could land first.
          </p>
          <p>
            <code className="mono">outcome</code> and <code className="mono">cost_eur</code> are
            null while a call is still running; the same rows are readable from the CLI today with{" "}
            <code className="mono">python -m convo sessions list</code>.
          </p>
        </EmptyState>
      </section>
    </div>
  );
}
