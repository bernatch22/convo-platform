/* The anatomy of a voice turn, drawn: one bar per stage, the end-to-end wait as the rail.
 *
 * The numbers are medians over this project's stored voice sessions, in
 * seconds (`turn_metrics` rounds to millisecond precision), so every label
 * here multiplies by 1000. A stage nobody measured says so in words — it is
 * never drawn as a zero-width bar, which would read as "instant".
 *
 * The stages are measured independently by the framework and overlap in real
 * time; they are laid end to end to show proportion, not to claim they sum to
 * the end-to-end figure. The caption says as much on screen.
 */

import type { LatencyMedians } from "../lib/api";

interface StageSpec {
  key: keyof LatencyMedians;
  label: string;
  note: string;
}

/** The four legs of a turn, in the order the caller lives through them. */
const STAGES: StageSpec[] = [
  {
    key: "end_of_turn_delay",
    label: "end of turn",
    note: "silence the turn detector waits through before it believes the caller stopped",
  },
  {
    key: "transcription_delay",
    label: "transcription",
    note: "from the end of speech to Soniox's final transcript",
  },
  { key: "llm_node_ttft", label: "llm ttft", note: "to Haiku's first token" },
  { key: "tts_node_ttfb", label: "tts ttfb", note: "to ElevenLabs' first audio byte" },
];

interface WaterfallProps {
  medians: LatencyMedians;
  sessions: number;
  turns: number;
  /** Which project these medians are over — the empty state has to name it. */
  project: string;
}

export function Waterfall({ medians, sessions, turns, project }: WaterfallProps) {
  const stages = STAGES.map((stage) => ({ ...stage, seconds: medians[stage.key] }));
  const measured = stages.reduce((total, stage) => total + (stage.seconds ?? 0), 0);
  const rail = Math.max(measured, medians.e2e_latency ?? 0);

  if (rail === 0) {
    return <p className="note note--warn">{nothingMeasured(sessions, project)}</p>;
  }

  let offset = 0;
  return (
    <div className="wf">
      {stages.map((stage) => {
        const start = offset;
        offset += stage.seconds ?? 0;
        return (
          <Bar
            key={stage.key}
            label={stage.label}
            note={stage.note}
            seconds={stage.seconds}
            start={start}
            rail={rail}
          />
        );
      })}

      <Bar
        label="e2e"
        note="what the caller actually waits: their last word to the agent's first audio"
        seconds={medians.e2e_latency}
        start={0}
        rail={rail}
        total
      />

      <p className="wf__caption">
        medians over {sessions} voice session{sessions === 1 ? "" : "s"} · {turns} turns. The four
        stages are measured independently and overlap in real time; they are laid end to end to
        show proportion, not to claim they add up to e2e.
      </p>
    </div>
  );
}

interface BarProps {
  label: string;
  note: string;
  seconds: number | null;
  start: number;
  rail: number;
  total?: boolean;
}

function Bar({ label, note, seconds, start, rail, total }: BarProps) {
  return (
    <div className={total ? "wf__row wf__row--total" : "wf__row"}>
      <div className="wf__label" title={note}>
        {label}
      </div>
      <div className="wf__track">
        {seconds === null ? (
          <span className="wf__unmeasured">not yet measured</span>
        ) : (
          <span
            className="wf__bar"
            style={{ left: percent(start, rail), width: percent(seconds, rail) }}
          />
        )}
      </div>
      <div className="wf__value mono">{seconds === null ? "—" : `${ms(seconds)} ms`}</div>
      <p className="wf__note">{note}</p>
    </div>
  );
}

function nothingMeasured(sessions: number, project: string): string {
  if (sessions === 0) {
    return `no voice session stored for ${project} yet — place one call and the bars appear.`;
  }
  const plural = sessions === 1 ? "" : "s";
  return `${sessions} stored voice session${plural} for ${project}, and not one turn carries a latency — a text session measures none.`;
}

function ms(seconds: number): number {
  return Math.round(seconds * 1000);
}

function percent(value: number, rail: number): string {
  return `${Math.max((value / rail) * 100, value > 0 ? 0.6 : 0)}%`;
}
