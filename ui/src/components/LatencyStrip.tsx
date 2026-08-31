/* The four legs of one call's latency, median and max — the terminal's numbers, on screen.
 *
 * Nothing new is measured here: every value is the median (or the max) of the
 * per-turn chips `python -m convo sessions show <id>` already prints, in the
 * same seconds and the same two decimals, so the two readings can be held
 * side by side and disagreeing would be a bug.
 */

import { LEG_LABEL, seconds, type LegStat } from "../lib/sessions";

export function LatencyStrip({ stats }: { stats: LegStat[] }) {
  const measured = stats.filter((stat) => stat.turns > 0);
  if (measured.length === 0) {
    return (
      <p className="note">
        No turn in this session carried a metric — a chat session times nothing, and a voice call
        that dropped before its first answer has nothing to time.
      </p>
    );
  }

  return (
    <div className="strip">
      {measured.map((stat) => (
        <div key={stat.leg} className="strip__cell">
          <div className="strip__leg">{LEG_LABEL[stat.leg]}</div>
          <div className="strip__median">{seconds(stat.median)}</div>
          <div className="strip__foot">
            <span>
              max <span className="strip__max">{seconds(stat.max)}</span>
            </span>
            <span className="faint">
              n={stat.turns}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
