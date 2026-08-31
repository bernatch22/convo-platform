/* The consent proof: which grant paid for which irreversible act, stated as a sentence.
 *
 * This is the one panel on the screen that is evidence rather than telemetry.
 * `guard.check` refuses an irreversible tool without a token minted by
 * `ConfirmTask`, so a booking that happened MUST have a `confirm.granted`
 * before it in the log — and if it does not, the absence is the finding. The
 * link is drawn by seq in both directions so a reader can jump to either row.
 */

import type { ConsentLink } from "../lib/sessions";

export function ConsentProof({ links }: { links: ConsentLink[] }) {
  if (links.length === 0) {
    return (
      <p className="note">
        Nothing in this call needed a confirmation: no tool with{" "}
        <code className="mono">side_effect: irreversible</code> was reached.
      </p>
    );
  }

  return (
    <ul className="consent">
      {links.map((link) => (
        <li key={link.audience} className={`consent__item consent__item--${verdictOf(link)}`}>
          <div className="consent__head">
            <span className="consent__verb">{verdictOf(link)}</span>
            <span className="tool mono">{link.tool}</span>
            {link.sideEffect && (
              <span className={`effect effect--${link.sideEffect}`}>{link.sideEffect}</span>
            )}
          </div>
          <p className="consent__sentence">{sentenceOf(link)}</p>
          <div className="consent__audience mono">{link.audience}</div>
        </li>
      ))}
    </ul>
  );
}

/** `granted`, `declined`, or `unanswered` — what the log says the caller did. */
function verdictOf(link: ConsentLink): string {
  if (link.granted !== null) return "granted";
  if (link.declined !== null) return "declined";
  return "unanswered";
}

/** The proof in one line, in seqs, so it can be checked against the rows below. */
function sentenceOf(link: ConsentLink): string {
  const asked = link.requested === null ? "the question is not in the log" : `seq ${link.requested}`;
  if (link.granted !== null && link.authorised !== null) {
    return `${asked} asked; seq ${link.granted} authorised seq ${link.authorised}.`;
  }
  if (link.granted !== null) {
    return `${asked} asked; seq ${link.granted} granted it — and no tool call followed.`;
  }
  if (link.declined !== null) {
    return `${asked} asked; seq ${link.declined} declined it, so nothing irreversible ran.`;
  }
  return `${asked} asked, and the call ended before an answer — nothing irreversible ran.`;
}
