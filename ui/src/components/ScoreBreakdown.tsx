/* The post-call score, check by check, with what it cost to reach.
 *
 * The panel is ordered the way the scorer runs: everything code decided first,
 * then the one judged metric, then the bill. That order is the argument — the
 * expensive opinion is last and optional, and a reader can see that four of
 * the five verdicts on this screen cost nothing and cannot drift.
 *
 * A check that did not apply is drawn dim with a dash rather than green: a
 * project with no register declared has not passed the register check, and a
 * panel that pretended otherwise would be the console lying about coverage.
 */

import type { SessionScore } from "../lib/api";
import { euros } from "../lib/sessions";

export function ScoreBreakdown({ score }: { score: SessionScore | null }) {
  if (!score) {
    return (
      <p className="note">
        This call has no score. Either the control plane has not reached it yet, it was too short
        to judge, or its project has <code className="mono">scoring=False</code>. Ask for one with{" "}
        <code className="mono">python -m convo sessions score &lt;id&gt;</code>.
      </p>
    );
  }

  return (
    <div className="panel">
      <div className="panel__body">
        <ul className="score-list">
          {score.checks.map((check) => (
            <li key={check.name} className={`score-row score-row--${stateOf(check.passed)}`}>
              <span className="score-row__mark">{markOf(check.passed)}</span>
              <span className="score-row__name mono">{check.name}</span>
              <span className="score-row__kind">{check.kind}</span>
              <span className="score-row__reason">{check.reason}</span>
              {check.score !== undefined && (
                <span className="score-row__value mono">{check.score.toFixed(2)}</span>
              )}
            </li>
          ))}
        </ul>
        <p className="note">{billOf(score)}</p>
      </div>
    </div>
  );
}

/** `pass`, `fail` or `na` — the three answers a check can give. */
function stateOf(passed: boolean | null): string {
  if (passed === null) return "na";
  return passed ? "pass" : "fail";
}

function markOf(passed: boolean | null): string {
  if (passed === null) return "–";
  return passed ? "✓" : "✗";
}

/** One sentence about the only part of this that cost money. */
function billOf(score: SessionScore): string {
  const judge = score.judge;
  const turns = `${score.turns} turns replayed from the log`;
  if (!judge) return `${turns}; the deterministic checks alone, and they cost nothing.`;
  if (!judge.ran) return `${turns}; the judge did not run — ${judge.skipped}.`;
  return `${turns}; ${judge.model} judged once for ${euros(judge.cost_eur)}, under the ${euros(
    judge.cap_eur,
  )} cap proved before the call was made.`;
}
