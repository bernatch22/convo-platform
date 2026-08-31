/* Evals — every run this fleet has scored, the button that starts another, and the diff between them.
 *
 * The screen answers three questions in the order an operator asks them: what
 * did the last run score, is it better or worse than the one before, and can I
 * run it again right now. The URL carries both pieces of state — `?project=`
 * narrows the table, `?run=` opens one run — so a regression is a link you can
 * paste to whoever wrote it.
 */

import { useLoaderData, useRevalidator, useSearchParams } from "react-router";

import { EmptyState } from "../components/EmptyState";
import { EvalLauncher } from "../components/EvalLauncher";
import { Delta, EvalScores } from "../components/EvalScores";
import { listEvalRuns, listEvalSuites, type EvalRun, type ProjectSuites } from "../lib/api";
import { startedAt } from "../lib/sessions";

const LIMIT = 200;

/** What this screen renders: what can be run, what has been run, and the refusal if neither loaded. */
export interface EvalsData {
  projects: ProjectSuites[];
  runs: EvalRun[];
  error: string | null;
}

/** Load the fleet's suites and its runs together; a dead control plane empties the screen. */
export async function evalsLoader(): Promise<EvalsData> {
  try {
    const [projects, runs] = await Promise.all([
      listEvalSuites(),
      listEvalRuns({ limit: LIMIT }),
    ]);
    return { projects, runs, error: null };
  } catch (cause) {
    const error = cause instanceof Error ? cause.message : String(cause);
    return { projects: [], runs: [], error };
  }
}

export function Evals() {
  const { projects, runs, error } = useLoaderData() as EvalsData;
  const [params, setParams] = useSearchParams();
  const revalidator = useRevalidator();

  const project = params.get("project");
  const selected = params.get("run");
  const shown = project ? runs.filter((run) => run.project === project) : runs;
  const open = runs.find((run) => run.id === selected) ?? null;

  const select = (next: Record<string, string | null>) => {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value === null) merged.delete(key);
      else merged.set(key, value);
    }
    setParams(merged);
  };

  return (
    <div className="page page--wide">
      <header className="page__head">
        <div className="page__eyebrow">fleet</div>
        <h1 className="page__title">Evals</h1>
        <p className="page__lede">
          Every project keeps goldens that grow with each card, and{" "}
          <code className="mono">deepeval test run</code> is part of a milestone&apos;s definition
          of done. This is where those runs are readable without a terminal: score per metric, per
          project, per run, and the delta against the previous run of the same suite.
        </p>
      </header>

      <section className="section">
        <h2 className="section__title">Run a suite</h2>
        <EvalLauncher
          projects={projects}
          onLanded={() => revalidator.revalidate()}
          onStarted={(id) => select({ run: id })}
        />
      </section>

      <section className="section">
        <h2 className="section__title">Runs</h2>

        {projects.length > 0 && (
          <nav className="tabs" aria-label="Projects">
            <button
              type="button"
              className={project ? "tabs__tab" : "tabs__tab is-active"}
              onClick={() => select({ project: null })}
            >
              all
            </button>
            {projects.map((row) => (
              <button
                key={`${row.tenant}/${row.project}`}
                type="button"
                className={row.project === project ? "tabs__tab is-active" : "tabs__tab"}
                onClick={() => select({ project: row.project })}
              >
                {row.project}
              </button>
            ))}
          </nav>
        )}

        {shown.length > 0 ? (
          <RunTable runs={shown} selected={selected} onSelect={(id) => select({ run: id })} />
        ) : (
          <EmptyState
            title={error ? "The control plane did not answer" : "No run has been stored yet"}
            milestone="ms-14"
            command="uv run deepeval test run tests/evals -n 3"
          >
            <p>
              {error ? (
                <>
                  <code className="mono">GET /evals/runs</code> failed with{" "}
                  <code className="mono">{error}</code>. Start it with{" "}
                  <code className="mono">uv run uvicorn api:app --port 8090</code>.
                </>
              ) : (
                <>
                  A run appears here the moment one finishes — launched from the button above, or
                  filed by a laptop or by CI through <code className="mono">POST /evals/runs</code>.
                </>
              )}
            </p>
          </EmptyState>
        )}
      </section>

      {open && (
        <section className="section">
          <h2 className="section__title">
            {open.project} · {open.suite}
          </h2>
          <RunDetail run={open} />
        </section>
      )}
    </div>
  );
}

/** Every run as one dense line; the metrics collapse into a chip each so a regression is visible. */
function RunTable({
  runs,
  selected,
  onSelect,
}: {
  runs: EvalRun[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <>
      <div className="table-wrap">
        <table className="table table--calls">
          <thead>
            <tr>
              <th>run</th>
              <th>project</th>
              <th>suite</th>
              <th>started</th>
              <th>status</th>
              <th>scores</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr
                key={run.id}
                className={run.id === selected ? "ev__row is-open" : "ev__row"}
                onClick={() => onSelect(run.id)}
              >
                <td className="id">
                  <button type="button" className="link ev__open">
                    {run.id}
                  </button>
                </td>
                <td className="dim mono">{run.project}</td>
                <td className="mono">{run.suite}</td>
                <td className="mono dim">{startedAt(run.started_at)}</td>
                <td>
                  <span className={`outcome ev__status--${run.status}`}>{run.status}</span>
                </td>
                <td>
                  <span className="chips">
                    {run.metrics.map((metric) => (
                      <span className="chip" key={metric.metric}>
                        <span className="chip__key">{metric.metric}</span>
                        <span className="chip__val">{metric.score.toFixed(2)}</span>
                        <Delta value={metric.delta} />
                      </span>
                    ))}
                    {run.metrics.length === 0 && <span className="faint mono">—</span>}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">
        {runs.length} run{runs.length === 1 ? "" : "s"} · the same rows{" "}
        <code className="mono">curl -s localhost:8090/evals/runs</code> prints
      </p>
    </>
  );
}

/** One run in full: the score table with its diff, the commit it ran on, the evidence it left. */
function RunDetail({ run }: { run: EvalRun }) {
  return (
    <div className="ev__detail">
      <table className="kv">
        <tbody>
          <tr>
            <td className="kv__key">run</td>
            <td className="kv__val mono">{run.id}</td>
          </tr>
          <tr>
            <td className="kv__key">commit</td>
            <td className="kv__val mono">{run.git_sha ?? "unknown"}</td>
          </tr>
          <tr>
            <td className="kv__key">status</td>
            <td className="kv__val">
              <span className={`outcome ev__status--${run.status}`}>{run.status}</span>
              {run.detail && <span className="dim"> · {run.detail}</span>}
            </td>
          </tr>
          <tr>
            <td className="kv__key">evidence</td>
            <td className="kv__val mono">{run.report_html ?? run.log_path ?? "—"}</td>
          </tr>
        </tbody>
      </table>

      <EvalScores metrics={run.metrics} previous={run.previous} />
    </div>
  );
}
