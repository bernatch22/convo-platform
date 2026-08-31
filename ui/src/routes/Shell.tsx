/* The frame every screen hangs in: brand, header strip, left rail, work surface. */

import { Outlet, useRouteLoaderData } from "react-router";

import { Header } from "../components/Header";
import { Rail } from "../components/Rail";
import { listTenants, type Tenant } from "../lib/api";

/** What the whole app knows before any screen renders: who this deploy serves. */
export interface ShellData {
  tenants: Tenant[];
  error: string | null;
}

/** Load the switcher's tenants; a dead control plane dims the shell, it does not kill it. */
export async function shellLoader(): Promise<ShellData> {
  try {
    return { tenants: await listTenants(), error: null };
  } catch (cause) {
    return { tenants: [], error: cause instanceof Error ? cause.message : String(cause) };
  }
}

/** Read the shell's tenants from any screen below it. */
export function useShellData(): ShellData {
  return useRouteLoaderData("root") as ShellData;
}

export function Shell() {
  const { tenants } = useShellData();

  return (
    <div className="shell">
      <div className="shell__brand">
        <span className="brand__mark" aria-hidden />
        <span className="brand__name">convo</span>
        <span className="brand__kind">ops</span>
      </div>

      <div className="shell__header">
        <Header />
      </div>

      <nav className="shell__rail" aria-label="Tenants and sections">
        <Rail tenants={tenants} />
      </nav>

      <main className="shell__main">
        <Outlet />
      </main>
    </div>
  );
}
