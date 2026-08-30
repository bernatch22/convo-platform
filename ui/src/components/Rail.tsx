/* The switcher and the section links — navigation, never state.
 *
 * Every entry is a NavLink: picking a project changes the URL, and the URL is
 * what every screen below reads. There is nothing to keep in sync.
 */

import { NavLink, useParams } from "react-router";

import type { Tenant } from "../lib/api";

import { ConnectionDot } from "./ConnectionDot";

interface RailProps {
  tenants: Tenant[];
}

const SECTIONS = [
  { to: "sessions", label: "Sessions", glyph: "≡" },
  { to: "pipeline", label: "Pipeline", glyph: "⇄" },
] as const;

export function Rail({ tenants }: RailProps) {
  const { tenant: current } = useParams();
  const active = current ?? tenants[0]?.tenant;

  return (
    <>
      <div className="rail__group">
        <div className="rail__label">
          <span>Tenants</span>
          <ConnectionDot />
        </div>

        {tenants.length === 0 && (
          <div className="rail__tenant faint">no tenant answering</div>
        )}

        {tenants.map((tenant) => (
          <div key={tenant.tenant}>
            <div className="rail__tenant">{tenant.tenant}</div>
            {tenant.projects.map((project) => (
              <NavLink
                key={project.id}
                to={`/t/${tenant.tenant}/${project.id}`}
                className={link("rail__link rail__link--project")}
              >
                <span className="rail__glyph">▸</span>
                <span>{project.id}</span>
                <span className="rail__tag">{project.language}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </div>

      {active && (
        <div className="rail__group">
          <div className="rail__label">
            <span>{active}</span>
          </div>
          {SECTIONS.map((section) => (
            <NavLink
              key={section.to}
              to={`/t/${active}/${section.to}`}
              className={link("rail__link")}
            >
              <span className="rail__glyph">{section.glyph}</span>
              <span>{section.label}</span>
            </NavLink>
          ))}
        </div>
      )}

      <div className="rail__group">
        <div className="rail__label">
          <span>Fleet</span>
        </div>
        <NavLink to="/evals" className={link("rail__link")}>
          <span className="rail__glyph">✓</span>
          <span>Evals</span>
        </NavLink>
        <NavLink to="/supervisor" className={link("rail__link")}>
          <span className="rail__glyph">◎</span>
          <span>Supervisor</span>
        </NavLink>
      </div>

      <div className="rail__foot">
        <div>voice · chat · phone</div>
        <div>+1 417 674 3169</div>
      </div>
    </>
  );
}

function link(base: string) {
  return ({ isActive }: { isActive: boolean }) => (isActive ? `${base} is-active` : base);
}
