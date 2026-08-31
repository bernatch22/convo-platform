/* The one button on this console that spends money, and the log that proves it is spending it.
 *
 * The box runs ONE eval at a time and refuses a second with a 409, so every
 * button here goes dead the moment one starts: the refusal is a rule, not a
 * race the operator has to win. While the child runs, its own output is on
 * screen — nothing is launched blind and nothing is merely awaited.
 */

import { useState } from "react";

import { ApiError, launchEvalRun, type EvalRunStatus, type ProjectSuites } from "../lib/api";
import { useEvalRun } from "../lib/useEvalRun";

interface EvalLauncherProps {
  projects: ProjectSuites[];
  /** Called when a run lands, so the list below refetches with the new line in it. */
  onLanded: () => void;
  /** Called when a run starts, so the URL can select it. */
  onStarted: (id: string) => void;
}

export function EvalLauncher({ projects, onLanded, onStarted }: EvalLauncherProps) {
  const [active, setActive] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useEvalRun(active, () => {
    setActive(null);
    onLanded();
  });

  const launch = async (tenant: string, project: string, suite: string) => {
    setError(null);
    try {
      const started = await launchEvalRun({ tenant, project, suite });
      setActive(started.id);
      onStarted(started.id);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : String(cause));
    }
  };

  return (
    <>
      <div className="ev__launch">
        {projects.map((project) => (
          <div className="panel" key={`${project.tenant}/${project.project}`}>
            <div className="panel__head">
              <span className="panel__title">{project.project}</span>
              <span className="badge">{project.tenant}</span>
            </div>
            <div className="panel__body">
              {project.suites.length === 0 ? (
                <p className="note">
                  declares no suite — add one to <code className="mono">evals/suites.json</code>
                </p>
              ) : (
                <div className="ev__suites">
                  {project.suites.map((suite) => (
                    <button
                      key={suite}
                      type="button"
                      className="button ev__run"
                      disabled={active !== null}
                      onClick={() => void launch(project.tenant, project.project, suite)}
                    >
                      Run {suite}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {error && <p className="ctl__error">{error}</p>}
      {run && <Live run={run} />}
    </>
  );
}

/** The run in flight: what it is, how long it has been going, and what it is writing. */
function Live({ run }: { run: EvalRunStatus }) {
  const going = run.status === "running";

  return (
    <div className="ev__live">
      <div className="ev__liveHead">
        <span className={going ? "ev__dot ev__dot--live" : "ev__dot"} aria-hidden />
        <span className="mono">
          {run.project} · {run.suite}
        </span>
        <span className="dim">{going ? "running" : run.status}</span>
        <span className="faint mono">{run.id}</span>
      </div>
      <pre className="ev__log">{run.log.join("\n") || "waiting for the first line…"}</pre>
      <p className="note">
        one run at a time, killed at fifteen minutes · the full log is at{" "}
        <code className="mono">{run.log_path ?? "tmp/evals/"}</code>
      </p>
    </div>
  );
}
