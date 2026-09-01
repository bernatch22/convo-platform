/* One strip of bars per verb: how many times the platform did that thing, day by day.
 *
 * Small multiples rather than a stack. The palette has exactly one accent and
 * spending it on "here is a verb" would need a second and a third colour that
 * tokens.css does not have — so each verb keeps its own row, every row shares
 * one vertical scale, and comparing two verbs is a glance down the page
 * instead of a squint at a legend.
 *
 * The only inline style is a percentage height. Numbers may be computed;
 * colours may not.
 */

import type { OutcomeDay, OutcomeVerb } from "../lib/api";

interface OutcomeBarsProps {
  series: OutcomeDay[];
  verbs: OutcomeVerb[];
}

export function OutcomeBars({ series, verbs }: OutcomeBarsProps) {
  const ceiling = Math.max(1, ...series.flatMap((day) => Object.values(day.verbs)));

  return (
    <div className="bars">
      {verbs.map((tally) => (
        <div key={tally.verb} className="bars__row">
          <div className="bars__name mono">{tally.verb}</div>
          <div className="bars__track">
            {series.map((day) => (
              <Bar key={day.day} day={day} verb={tally.verb} ceiling={ceiling} />
            ))}
          </div>
          <div className="bars__count num">{tally.count}</div>
        </div>
      ))}

      <div className="bars__axis">
        <span className="bars__name" />
        <div className="bars__span">
          <span>{dayLabel(series[0]?.day)}</span>
          <span className="faint">peak {ceiling} / day</span>
          <span>{dayLabel(series[series.length - 1]?.day)}</span>
        </div>
        <span className="bars__count" />
      </div>
    </div>
  );
}

/** One day of one verb. A day with nothing in it keeps its column and draws no fill. */
function Bar({ day, verb, ceiling }: { day: OutcomeDay; verb: string; ceiling: number }) {
  const count = day.verbs[verb] ?? 0;
  const height = count === 0 ? 0 : Math.max(8, Math.round((count / ceiling) * 100));

  return (
    <div className="bars__day" title={`${day.day} · ${verb} · ${count}`}>
      <div className="bars__fill" style={{ height: `${height}%` }} />
    </div>
  );
}

/** `Aug 29` — the axis names two days, not fourteen. */
function dayLabel(day: string | undefined): string {
  if (!day) return "";
  return new Date(`${day}T12:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "2-digit",
  });
}
