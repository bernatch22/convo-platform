/* The phone door of ONE project: the numbers that reach it, or the fact that none do.
 *
 * A number belongs to a route, not to the fleet and not to the chrome of this
 * console. Printing one in the sidebar under every tenant said the opposite —
 * that every project shares the trunk — which is false today and would stay
 * false the moment a second number arrives. So the line is rendered beside the
 * project it actually rings into, and a project with no line says exactly that
 * instead of borrowing somebody else's.
 *
 * Two screens ask for it and both get THIS component: Pipeline, where the line
 * is one leg of a configuration and the control plane's paragraph under it is
 * the point, and Talk, where a human who wants to be called is looking at the
 * project's own page and should not have to open another screen to find the
 * number. Only the wrapper differs — a section panel or one strip under a page
 * title. The rows, their classes and the number's formatting are the same code
 * in both, so the two screens cannot drift into printing a number differently.
 *
 * Every string but the labels comes from GET /pipeline: the note explaining a
 * line, or its absence, is the control plane's own sentence, printed verbatim.
 */

import type { PhoneLine as Line, PhoneSnapshot } from "../lib/api";

/** Where these lines are being shown: a section panel, or one strip under a page title. */
export type PhoneFrame = "panel" | "header";

export function PhoneLines({
  phone,
  frame = "panel",
}: {
  phone: PhoneSnapshot;
  frame?: PhoneFrame;
}) {
  const label = phone.lines.length ? "inbound line" : "no inbound line";

  if (frame === "header") {
    return (
      <div className="dial dial--header">
        <span className="dial__label">{label}</span>
        <Lines phone={phone} />
      </div>
    );
  }

  return (
    <article className="panel">
      <div className="panel__head">
        <span className="panel__title">{label}</span>
        <span className="badge">fleet {phone.fleet}</span>
      </div>
      <div className="panel__body dial dial--panel">
        <Lines phone={phone} />
        {phone.lines.length > 0 && <p className="leg__note">{phone.note}</p>}
      </div>
    </article>
  );
}

/** The lines themselves, or the control plane's sentence saying there are none. */
function Lines({ phone }: { phone: PhoneSnapshot }) {
  if (phone.lines.length === 0) {
    return <p className="dial__none">{phone.note}</p>;
  }

  return (
    <>
      {phone.lines.map((line) => (
        <LineRow key={`${line.fleet}:${line.number}`} line={line} />
      ))}
    </>
  );
}

function LineRow({ line }: { line: Line }) {
  return (
    <div className="dial__line">
      <span className="dial__number mono">{readable(line.number)}</span>
      <span className="dial__meta mono dim">
        {line.channel} · fleet {line.fleet}
      </span>
      {!line.serving && (
        <p className="dial__warn">
          this number is routed to another fleet — no call on it reaches this deploy
        </p>
      )}
    </div>
  );
}

/** E.164 grouped the way the number is read aloud; an unrecognised country prints untouched.
 *
 * The control plane stores and dials E.164 and must keep doing so — this is a
 * reading of the same digits, never a second spelling of the number, so no
 * caller can be dialled from what this function returns.
 */
function readable(number: string): string {
  const digits = number.replace(/\D/g, "");

  // North America: +1 NPA NXX XXXX.
  if (number.startsWith("+1") && digits.length === 11) {
    return `+1 ${digits.slice(1, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
  }

  // Spain: +34 XXX XX XX XX.
  if (number.startsWith("+34") && digits.length === 11) {
    const rest = digits.slice(2);
    return `+34 ${rest.slice(0, 3)} ${rest.slice(3, 5)} ${rest.slice(5, 7)} ${rest.slice(7)}`;
  }

  return number;
}
