/* The score of a finished call, as one chip an operator scans a column of.
 *
 * A null score is a dash and never a zero. It means one of three things — not
 * scored yet, too short to judge, or a project that opted out — and all three
 * are "no opinion", which is the opposite of a bad call. The tooltip says
 * which, so a column of dashes is readable without opening a row.
 */

import type { SessionScore } from "../lib/api";
import { scoreTitle } from "../lib/sessions";

export function ScoreChip({ score, running }: { score: SessionScore | null; running?: boolean }) {
  if (!score) {
    return (
      <span className="score score--none" title={scoreTitle(null, running)}>
        —
      </span>
    );
  }

  return (
    <span className={`score score--${score.verdict}`} title={scoreTitle(score)}>
      {score.score.toFixed(2)}
      {score.failed.length > 0 && <span className="score__failed">{score.failed.join(" ")}</span>}
    </span>
  );
}
