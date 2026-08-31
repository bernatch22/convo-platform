/* The tenant-scoped URLs this console had before sections moved under a project.
 *
 * `/t/<tenant>/pipeline` named the business but never the project, so the
 * screen had to guess one — the bug this file exists to have removed. The old
 * shapes stay alive as redirects: a bookmark lands on the project it meant,
 * never on a 404. A legacy session link is resolved through the session
 * itself, so it lands on the project that actually held the call.
 */

import { redirect, type LoaderFunctionArgs } from "react-router";

import { getSession, listTenants } from "../lib/api";
import { sectionPath, type Section } from "../lib/nav";

/** `/t/<tenant>` → that tenant's first project. */
export async function legacyTenantLoader({ params }: LoaderFunctionArgs): Promise<Response> {
  return redirect(await landing(params["tenant"] ?? "", null, "talk"));
}

/** `/t/<tenant>/sessions` → the same call log, scoped to the tenant's first project. */
export async function legacySessionsLoader({ params }: LoaderFunctionArgs): Promise<Response> {
  return redirect(await landing(params["tenant"] ?? "", null, "sessions"));
}

/** `/t/<tenant>/sessions/<id>` → that session under the project that recorded it. */
export async function legacySessionDetailLoader({
  params,
}: LoaderFunctionArgs): Promise<Response> {
  const id = params["id"] ?? "";
  const held = await holderOf(id);
  const tenant = held?.tenant ?? params["tenant"] ?? "";
  const base = await landing(tenant, held?.project ?? null, "sessions");
  return redirect(base === "/" ? base : `${base}/${encodeURIComponent(id)}`);
}

/** `/t/<tenant>/pipeline?project=x` → `/t/<tenant>/x/pipeline`; the query becomes the path. */
export async function legacyPipelineLoader({
  params,
  request,
}: LoaderFunctionArgs): Promise<Response> {
  const wanted = new URL(request.url).searchParams.get("project");
  return redirect(await landing(params["tenant"] ?? "", wanted, "pipeline"));
}

/** Where a legacy URL should land: the project it asked for, else the tenant's first. */
async function landing(tenant: string, wanted: string | null, section: Section): Promise<string> {
  if (wanted) return sectionPath(tenant, wanted, section);

  const first = await firstProject(tenant);
  return first ? sectionPath(tenant, first, section) : "/";
}

/** The tenant's first project, or null — a dead control plane sends the reader home, not to a 404. */
async function firstProject(tenant: string): Promise<string | null> {
  try {
    const row = (await listTenants()).find((known) => known.tenant === tenant);
    return row?.projects[0]?.id ?? null;
  } catch {
    return null;
  }
}

/** Which tenant and project a session belongs to, read off the session itself. */
async function holderOf(id: string): Promise<{ tenant: string; project: string } | null> {
  try {
    const view = await getSession(id);
    return { tenant: view.tenant, project: view.project };
  } catch {
    return null;
  }
}
