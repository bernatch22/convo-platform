/* The switcher and the section links — navigation, never state.
 *
 * Every entry is a link: picking a project changes the URL, and the URL is what
 * every screen below reads. There is nothing to keep in sync.
 *
 * Which project you are standing in is read straight off the path, so it stays
 * highlighted on every screen — Talk, Sessions, Pipeline, one session's log —
 * and the section group is labelled with the tenant and project it acts on.
 * Picking another project keeps you on the section you were reading.
 */

import { NavLink, useLocation, useParams } from "react-router";

import type { Tenant } from "../lib/api";
import { SECTIONS, sectionOf, sectionPath } from "../lib/nav";

import { ConnectionDot } from "./ConnectionDot";

interface RailProps {
  tenants: Tenant[];
}

const FLEET = ["evals", "supervisor"] as const;

export function Rail({ tenants }: RailProps) {
  const { tenant, project } = useParams();
  const here = sectionOf(useLocation().pathname);

  const activeTenant = tenant ?? tenants[0]?.tenant;
  const known = tenants.find((row) => row.tenant === activeTenant);
  const activeProject = project ?? known?.projects[0]?.id;

  // On a fleet screen there is no section to stay in, so a project link opens Talk.
  const carry = here ?? "talk";

  return (
    <>
      <div className="rail__group">
        <div className="rail__label">
          <span>Tenants</span>
          <ConnectionDot />
        </div>

        {tenants.length === 0 && <div className="rail__tenant faint">no tenant answering</div>}

        {tenants.map((row) => (
          <div key={row.tenant}>
            <div className="rail__tenant">{row.tenant}</div>
            {row.projects.map((entry) => (
              <NavLink
                key={entry.id}
                to={sectionPath(row.tenant, entry.id, carry)}
                className={mark(
                  "rail__link rail__link--project",
                  row.tenant === activeTenant && entry.id === activeProject,
                )}
              >
                <span>{entry.id}</span>
                <span className="rail__tag">{entry.language}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </div>

      {activeTenant && activeProject && (
        <div className="rail__group">
          <div className="rail__label rail__label--path">
            {activeTenant} / {activeProject}
          </div>
          {SECTIONS.map((section) => (
            <NavLink
              key={section}
              to={sectionPath(activeTenant, activeProject, section)}
              className={mark("rail__link", section === here)}
            >
              {label(section)}
            </NavLink>
          ))}
        </div>
      )}

      <div className="rail__group">
        <div className="rail__label">Fleet</div>
        {FLEET.map((section) => (
          <NavLink key={section} to={`/${section}`} className={link("rail__link")}>
            {label(section)}
          </NavLink>
        ))}
      </div>

      {/* No number here: a phone line belongs to ONE project's route, and printing
          the fleet's only number under every tenant made them all look reachable.
          The Pipeline screen names each project's line, or says it has none. */}
      <div className="rail__foot">
        <div>voice · chat · phone</div>
        <div>numbers per project · Pipeline</div>
      </div>
    </>
  );
}

/** Active by what the path says, not by what this link points at — a project link carries a section. */
function mark(base: string, active: boolean): string {
  return active ? `${base} is-active` : base;
}

function link(base: string) {
  return ({ isActive }: { isActive: boolean }) => (isActive ? `${base} is-active` : base);
}

function label(section: string): string {
  return section.charAt(0).toUpperCase() + section.slice(1);
}
