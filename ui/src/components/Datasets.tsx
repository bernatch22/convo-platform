/* The datasets on screen: what every suite of every project actually asks of the agent.
 *
 * A score is only worth what the case behind it asked. This is that case, in
 * the words the business wrote it in: the caller's line, the behaviour a
 * reviewer expects back, the tools that must have run — and, for ring 2, the
 * persona, the objective and the hard policies the whole call must survive.
 *
 * Read-only on purpose. Goldens are edited in git, where the change is
 * reviewed next to the prompt it grades; a screen that let anybody retype one
 * would be a screen that quietly moves the bar.
 */

import type { CallGolden, ProjectGoldens, SuiteGoldens, TurnGolden } from "../lib/api";

/** Every project's suites, each with the cases a run of it scores. */
export function Datasets({ datasets }: { datasets: ProjectGoldens[] }) {
  return (
    <div className="ds">
      {datasets.map((project) => (
        <section className="ds__project" key={`${project.tenant}/${project.project}`}>
          <h3 className="ds__projectName">
            <span className="dim">{project.tenant}</span> / {project.project}
          </h3>
          {project.suites.map((suite) => (
            <Suite key={suite.suite} suite={suite} />
          ))}
        </section>
      ))}
    </div>
  );
}

/** One suite: what it runs, how many cases it scores, and every one of them. */
function Suite({ suite }: { suite: SuiteGoldens }) {
  return (
    <article className="ds__suite">
      <header className="ds__head">
        <span className="ds__suiteName mono">{suite.suite}</span>
        <span className="ds__count">{countOf(suite)}</span>
        <span className="ds__target mono dim">{suite.dataset ?? suite.target}</span>
      </header>

      {suite.kind === "code" ? (
        <p className="note">
          This suite writes its cases in python rather than JSON — the personas it simulates live in{" "}
          <code className="mono">{suite.target}</code>.
        </p>
      ) : (
        <ol className="ds__cards">
          {suite.goldens.map((golden, index) => (
            <li className="ds__card" key={keyOf(golden, index)}>
              {isTurn(golden) ? <Turn golden={golden} /> : <Call golden={golden} />}
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}

/** One turn: the line the caller says, and what must come back for the case to pass. */
function Turn({ golden }: { golden: TurnGolden }) {
  return (
    <>
      <p className="ds__said">{golden.input}</p>
      <p className="ds__expect">{golden.expected_behaviour}</p>
      <span className="chips">
        {golden.turn && (
          <span className="chip">
            <span className="chip__key">turn</span>
            <span className="chip__val">{golden.turn}</span>
          </span>
        )}
        {golden.expected_tools.map((tool) => (
          <span className="chip" key={tool}>
            <span className="chip__key">tool</span>
            <span className="chip__val">{tool}</span>
          </span>
        ))}
        {golden.expected_tools.length === 0 && (
          <span className="chip">
            <span className="chip__key">tools</span>
            <span className="chip__val">none</span>
          </span>
        )}
      </span>
    </>
  );
}

/** One whole call: who is on the line, what they came for, and the policies that must hold. */
function Call({ golden }: { golden: CallGolden }) {
  return (
    <>
      <p className="ds__name mono">{golden.name}</p>
      <p className="ds__expect">{golden.objective}</p>
      <ol className="ds__turns">
        {golden.turns.map((line, index) => (
          <li className="ds__said" key={`${index}-${line.slice(0, 24)}`}>
            {line}
          </li>
        ))}
      </ol>
      <span className="chips">
        <span className="chip">
          <span className="chip__key">persona</span>
          <span className="chip__val">{golden.persona}</span>
        </span>
        {golden.max_turns !== null && (
          <span className="chip">
            <span className="chip__key">max turns</span>
            <span className="chip__val">{golden.max_turns}</span>
          </span>
        )}
        {golden.policies.map((policy) => (
          <span className="chip ds__policy" key={policy}>
            <span className="chip__key">must hold</span>
            <span className="chip__val">{policy}</span>
          </span>
        ))}
      </span>
    </>
  );
}

/** A ring-1 golden is the one with a caller's line in it; a ring-2 golden has a name. */
function isTurn(golden: TurnGolden | CallGolden): golden is TurnGolden {
  return "input" in golden;
}

/** What the header says next to the suite id: the number a run of it will score. */
function countOf(suite: SuiteGoldens): string {
  if (suite.count === null) return "cases in code";
  return `${suite.count} golden${suite.count === 1 ? "" : "s"}`;
}

/** Stable enough for a list that never reorders: the case's own name, else its position. */
function keyOf(golden: TurnGolden | CallGolden, index: number): string {
  return isTurn(golden) ? `${index}-${golden.input.slice(0, 24)}` : golden.name;
}
