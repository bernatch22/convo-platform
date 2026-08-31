/* Evals — the fleet's DeepEval runs. Empty until ms-16 puts a reader in front of them. */

import { EmptyState } from "../components/EmptyState";

export function Evals() {
  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">fleet</div>
        <h1 className="page__title">Evals</h1>
        <p className="page__lede">
          Every project keeps goldens that grow with each card, and{" "}
          <code className="mono">deepeval test run</code> is part of a milestone&apos;s definition
          of done. This screen is where those runs become readable without a terminal: score per
          metric, per project, per run, and the diff against the previous line.
        </p>
      </header>

      <EmptyState
        title="Runs live on disk, not in the API"
        milestone="ms-16 — evals on screen"
        card="not yet planned"
        command="uv run deepeval test run tests/evals -n 3"
      >
        <p>
          Today a run writes its HTML into <code className="mono">tmp/</code> and its verdict into
          the milestone report. Surfacing them here needs an endpoint that stores a run — which
          milestone, which commit, which goldens, which scores — and that is not built.
        </p>
        <p>
          The honest state of this screen is therefore: nothing to show, and the command above is
          the whole story until ms-16.
        </p>
      </EmptyState>
    </div>
  );
}
