/* The phone door of ONE project: the numbers that reach it, or the fact that none do.
 *
 * A number belongs to a route, not to the fleet and not to the chrome of this
 * console. Printing one in the sidebar under every tenant said the opposite —
 * that every project shares the trunk — which is false today and would stay
 * false the moment a second number arrives. So the line is rendered here,
 * beside the pipeline it actually rings into, and a project with no line says
 * exactly that instead of borrowing somebody else's.
 *
 * Every string but the labels comes from GET /pipeline: the note explaining a
 * line, or its absence, is the control plane's own sentence, printed verbatim.
 */

import type { PhoneLine as Line, PhoneSnapshot } from "../lib/api";

export function PhoneLines({ phone }: { phone: PhoneSnapshot }) {
  return (
    <article className="panel leg">
      <div className="panel__head">
        <span className="panel__title">
          {phone.lines.length ? "inbound line" : "no inbound line"}
        </span>
        <span className="badge">fleet {phone.fleet}</span>
      </div>
      <div className="panel__body">
        {phone.lines.length === 0 ? (
          <p className="note note--warn">{phone.note}</p>
        ) : (
          <>
            {phone.lines.map((line) => (
              <LineRow key={`${line.fleet}:${line.number}`} line={line} />
            ))}
            <p className="leg__note">{phone.note}</p>
          </>
        )}
      </div>
    </article>
  );
}

function LineRow({ line }: { line: Line }) {
  return (
    <div className="leg__row">
      <div className="leg__model mono">{line.number}</div>
      <div className="leg__v mono dim">
        {line.channel} · fleet {line.fleet}
      </div>
      {!line.serving && (
        <p className="note note--warn">
          this number is routed to another fleet — no call on it reaches this deploy
        </p>
      )}
    </div>
  );
}
