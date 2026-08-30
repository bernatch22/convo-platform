/* One session, read as its log: the seq table, the report, the live tail. */

import { Link, useParams } from "react-router";

import { EmptyState } from "../components/EmptyState";

const COLUMNS = ["seq", "t_ms", "kind", "payload"];

export function SessionDetail() {
  const { tenant = "", id = "" } = useParams();

  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">
          <Link to={`/t/${tenant}/sessions`}>{tenant} / sessions</Link>
        </div>
        <h1 className="page__title page__title--mono">{id}</h1>
        <p className="page__lede">
          The append-only log exactly as it was written: one row per fact, numbered and timed from
          sample zero. Live ≡ stored — the tail streams over SSE while the call is up, and reading
          it afterwards gives the same rows in the same order.
        </p>
      </header>

      <div className="table-wrap">
        <table className="table table--log">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column} className={column === "seq" || column === "t_ms" ? "num" : ""}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={COLUMNS.length} className="faint mono">
                no events — awaiting GET /sessions/{"{id}"} and /live
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section className="section">
        <EmptyState
          title="This log has no reader yet"
          milestone="ms-9"
          card="tk-667be6"
          command={`python -m convo sessions show ${id || "<id>"}`}
        >
          <p>
            The events exist. What this screen still needs is{" "}
            <code className="mono">GET /sessions/{"{id}"}</code> for the stored log and{" "}
            <code className="mono">/sessions/{"{id}"}/live</code> for the SSE tail, plus the report
            that <code className="mono">on_session_end</code> persists.
          </p>
        </EmptyState>
      </section>
    </div>
  );
}
