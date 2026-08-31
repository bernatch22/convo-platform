/* Follow one eval run until it stops running.
 *
 * A run is a subprocess on the box, not a stream: there is nothing to
 * subscribe to, so this polls `GET /evals/run/<id>` and stops the moment the
 * status is no longer "running". The log tail comes back on every poll, which
 * is what makes a run watchable instead of merely awaited.
 */

import { useEffect, useRef, useState } from "react";

import { getEvalRun, type EvalRunStatus } from "./api";

const POLL_MS = 1500;

/** Poll one run while it lives; `onLanded` fires once, when it stops running. */
export function useEvalRun(id: string | null, onLanded: () => void): EvalRunStatus | null {
  const [run, setRun] = useState<EvalRunStatus | null>(null);
  const landed = useRef(onLanded);
  landed.current = onLanded;

  useEffect(() => {
    if (!id) {
      setRun(null);
      return;
    }

    let stopped = false;
    let timer = 0;
    const controller = new AbortController();

    const tick = async () => {
      try {
        const next = await getEvalRun(id, controller.signal);
        if (stopped) return;
        setRun(next);
        if (next.status === "running") {
          timer = window.setTimeout(() => void tick(), POLL_MS);
        } else {
          landed.current();
        }
      } catch {
        // The control plane blinked or the run is gone: stop asking rather than
        // hammer a dead endpoint. The list below is still the record.
      }
    };

    void tick();
    return () => {
      stopped = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [id]);

  return run;
}
