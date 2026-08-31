/* The conversation itself: interim grey, final solid, and the agent filling word by word.
 *
 * Nothing here animates on a timer. The agent's words arrive from the SFU at
 * the pace ElevenLabs synthesises them (`sync_alignment=True`), so a word
 * appearing IS the word being spoken — the only job of this component is to
 * not get in the way, and to make each arrival visible with a short fade so
 * the line reads as karaoke rather than as text jumping.
 */

import { useEffect, useRef } from "react";

import { words, type AgentState, type Line } from "../lib/transcript";

interface TranscriptProps {
  lines: Line[];
  state: AgentState | null;
  empty: string;
}

export function Transcript({ lines, state, empty }: TranscriptProps) {
  const stream = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const box = stream.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [lines]);

  if (lines.length === 0) {
    return (
      <div className="stream stream--empty" ref={stream}>
        <p className="note">{empty}</p>
      </div>
    );
  }

  return (
    <div className="stream" ref={stream}>
      {lines.map((line) => (
        <Said key={line.id} line={line} />
      ))}
      {state === "thinking" && <p className="stream__state">thinking…</p>}
    </div>
  );
}

function Said({ line }: { line: Line }) {
  const classes = ["said", `said--${line.speaker}`, line.final ? "" : "said--interim"];

  return (
    <article className={classes.filter(Boolean).join(" ")}>
      <div className="said__who">{line.speaker}</div>
      <p className="said__text">
        {words(line.text).map((word, at) => (
          // Keyed by position on purpose: a word already on screen keeps its key and
          // therefore does not re-animate, so only the newly arrived one fades in.
          <span className="said__word" key={at}>
            {word}
          </span>
        ))}
        {!line.final && <span className="said__cursor" aria-hidden />}
      </p>
    </article>
  );
}
