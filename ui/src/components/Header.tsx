/* The header strip: where you are on the left, what build you are on on the right. */

import { Fragment, useState } from "react";
import { useLocation, useParams } from "react-router";

import { currentTheme, toggleTheme, type Theme } from "../lib/theme";

export function Header() {
  const crumbs = useCrumbs();

  return (
    <div className="header">
      <div className="header__crumbs">
        {crumbs.map((crumb, index) => (
          <Fragment key={crumb}>
            {index > 0 && <span className="header__sep">/</span>}
            {index === crumbs.length - 1 ? <b>{crumb}</b> : <span>{crumb}</span>}
          </Fragment>
        ))}
      </div>

      <div className="header__meta">
        <span className="meta">
          <span className="meta__key">env</span>
          <span className="meta__val">{__ENVIRONMENT__}</span>
        </span>
        <span className="meta">
          <span className="meta__key">build</span>
          <span className="meta__val">{__GIT_SHA__}</span>
        </span>
        <ThemeToggle />
      </div>
    </div>
  );
}

/** A hairline glyph that flips the console between daylight and dark. */
function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => currentTheme());
  const goingTo: Theme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(toggleTheme())}
      aria-label={`Switch to ${goingTo} theme`}
      title={goingTo}
    >
      {theme === "dark" ? <SunGlyph /> : <MoonGlyph />}
    </button>
  );
}

function SunGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path
        strokeLinecap="round"
        d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"
      />
    </svg>
  );
}

function MoonGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden>
      <path strokeLinejoin="round" d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />
    </svg>
  );
}

function useCrumbs(): string[] {
  const { pathname } = useLocation();
  const params = useParams();

  if (params.tenant) {
    const rest = pathname.split("/").slice(3).filter(Boolean);
    return ["fleet", params.tenant, ...rest];
  }
  const rest = pathname.split("/").filter(Boolean);
  return rest.length === 0 ? ["fleet"] : ["fleet", ...rest];
}
