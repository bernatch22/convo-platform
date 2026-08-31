/* Supervisor — the human on the other side of a warm transfer. Empty until ms-15. */

import { EmptyState } from "../components/EmptyState";

export function Supervisor() {
  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">fleet</div>
        <h1 className="page__title">Supervisor</h1>
        <p className="page__lede">
          Live calls across every tenant, the one an operator chooses to listen in on, and the
          hand-off itself: the agent introduces the caller, the human takes the line, the log keeps
          being written by the same session.
        </p>
      </header>

      <EmptyState
        title="There is nowhere to transfer to yet"
        milestone="ms-15 — transfers and the supervisor desk"
        card="not yet planned"
        command="uv run python -m convo sessions list"
      >
        <p>
          A warm transfer needs a destination that can accept one, so{" "}
          <code className="mono">REFER</code> and <code className="mono">WarmTransferTask</code>{" "}
          were deliberately deferred out of ms-11 to travel with this screen — a half-built desk
          would only be a place for calls to be dropped.
        </p>
        <p>
          What already exists underneath: the SIP leg, the per-number dispatch, and a log that a
          second participant can be appended to without breaking its ordering.
        </p>
      </EmptyState>
    </div>
  );
}
