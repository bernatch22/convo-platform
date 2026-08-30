/* One session, read as its log: the seq table, the report, and the live tail over SSE. */

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
                no events loaded
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section className="section">
        <EmptyState
          title="The log has an endpoint, not yet a reader"
          milestone="ms-9"
          card="the sessions card"
          command={`curl -s localhost:8090/sessions/${id || "<id>"}`}
        >
          <p>
            <code className="mono">GET /sessions/{"{id}"}</code> returns the stored log and the
            end-of-call report; <code className="mono">/sessions/{"{id}"}/live?after=&lt;seq&gt;</code>{" "}
            streams <code className="mono">open</code> / <code className="mono">append</code> /{" "}
            <code className="mono">end</code> frames as they are written. Both are typed in{" "}
            <code className="mono">lib/api.ts</code>; rendering them is the next card.
          </p>
        </EmptyState>
      </section>
    </div>
  );
}
