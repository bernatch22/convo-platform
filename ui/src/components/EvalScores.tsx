/* What a run scored, metric by metric, next to what the run before it scored.
 *
 * A score on its own is unreadable — 0.82 is good or bad only against the last
 * time the same suite ran. So the delta is a first-class column, not a
 * footnote, and a run with nothing to compare against says so in words.
 */

import type { MetricScore } from "../lib/api";

interface EvalScoresProps {
  metrics: MetricScore[];
  /** The run this one is diffed against; null means it is the first of its suite. */
  previous: string | null;
}

export function EvalScores({ metrics, previous }: EvalScoresProps) {
  if (metrics.length === 0) {
    return <p className="note">no metric scored — read the log below for what the suite did</p>;
  }

  return (
    <>
      <div className="table-wrap">
        <table className="table ev__scores">
          <thead>
            <tr>
              <th>metric</th>
              <th className="num">score</th>
              <th>vs previous</th>
              <th className="num">passed</th>
              <th className="num">failed</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((metric) => (
              <tr key={metric.metric}>
                <td className="mono">{metric.metric}</td>
                <td className="num">
                  <Bar metric={metric} />
                </td>
                <td>
                  <Delta value={metric.delta} />
                </td>
                <td className="num dim">{metric.passed}</td>
                <td className={metric.failed > 0 ? "num ev__bad" : "num faint"}>{metric.failed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">
        {previous
          ? `each delta is against run ${previous} — the previous scored run of this suite`
          : "first run of this suite: there is nothing to compare it against yet"}
      </p>
    </>
  );
}

/** A score reads faster as a length than as a number, so it is both. */
function Bar({ metric }: { metric: MetricScore }) {
  const width = `${Math.max(0, Math.min(1, metric.score)) * 100}%`;

  return (
    <span className="ev__score">
      <span className="ev__scoreValue">{metric.score.toFixed(2)}</span>
      <span className="ev__track">
        <span className={metric.failed > 0 ? "ev__bar ev__bar--bad" : "ev__bar"} style={{ width }} />
      </span>
    </span>
  );
}

/** Gained, lost, or first of its kind — the only three things a diff can say. */
export function Delta({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="faint mono">new</span>;
  }
  if (Math.abs(value) < 0.005) {
    return <span className="dim mono">±0.00</span>;
  }
  const kind = value > 0 ? "ev__delta ev__delta--up" : "ev__delta ev__delta--down";
  return (
    <span className={kind}>
      {value > 0 ? "+" : "−"}
      {Math.abs(value).toFixed(2)}
    </span>
  );
}
