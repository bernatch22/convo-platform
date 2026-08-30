/* Sessions — the call log for one tenant. The columns are real; the rows arrive with the read API. */

import { useParams } from "react-router";

import { EmptyState } from "../components/EmptyState";

const COLUMNS = ["session", "project", "channel", "started", "outcome", "turns", "cost"];

export function Sessions() {
  const { tenant = "" } = useParams();

  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">{tenant}</div>
        <h1 className="page__title">Sessions</h1>
        <p className="page__lede">
          Every conversation this tenant has had, newest first. A row opens the session&apos;s
          append-only log: one line per fact, numbered by <code className="mono">seq</code>, with
          the per-turn STT / LLM / TTS breakdown and the consent proof beside it.
        </p>
      </header>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column} className={column === "turns" || column === "cost" ? "num" : ""}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={COLUMNS.length} className="faint mono">
                no rows — awaiting GET /sessions
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <section className="section">
        <EmptyState
          title="The read side is not wired yet"
          milestone="ms-9"
          card="tk-667be6"
          command="python -m convo sessions list"
        >
          <p>
            Sessions are already being written — every call and every console run appends to the
            store as it happens. What is missing is <code className="mono">GET /sessions</code>, the
            endpoint that hands them to this table; it is being built alongside this shell.
          </p>
          <p>Until it lands, the same rows are readable from the CLI.</p>
        </EmptyState>
      </section>
    </div>
  );
}
