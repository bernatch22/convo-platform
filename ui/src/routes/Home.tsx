/* "/" is not a screen: it is a redirect to the first project this deploy can route to.
 *
 * If the control plane answered with nothing — or did not answer at all — that
 * is a real state and it gets said out loud rather than redirected away.
 */

import { Navigate } from "react-router";

import { EmptyState } from "../components/EmptyState";
import { sectionPath } from "../lib/nav";

import { useShellData } from "./Shell";

export function Home() {
  const { tenants, error } = useShellData();
  const first = tenants[0];
  const project = first?.projects[0];

  if (first && project) {
    return <Navigate replace to={sectionPath(first.tenant, project.id, "talk")} />;
  }

  return (
    <div className="page">
      <header className="page__head">
        <div className="page__eyebrow">fleet</div>
        <h1 className="page__title">Nothing routable</h1>
      </header>

      <EmptyState
        title={error ? "The control plane did not answer" : "This deploy serves no tenant"}
        command="uv run uvicorn api:app --port 8090"
      >
        {error ? (
          <p>
            <code className="mono">GET /tenants</code> failed with{" "}
            <code className="mono">{error}</code>. In development this shell proxies to port 8090;
            start the control plane there and this page will redirect itself.
          </p>
        ) : (
          <p>
            <code className="mono">GET /tenants</code> answered with an empty list, so the registry
            loaded no tenant. A tenant that fails to import is unroutable by design — it does not
            take the fleet down — so check the worker log for the import that broke.
          </p>
        )}
      </EmptyState>
    </div>
  );
}
