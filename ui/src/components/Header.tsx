/* The header strip: where you are on the left, what build you are on on the right. */

import { Fragment } from "react";
import { useLocation, useParams } from "react-router";

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
      </div>
    </div>
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
