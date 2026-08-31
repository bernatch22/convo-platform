/* The last screen: a route threw, or there is no such route. Say which, exactly. */

import { isRouteErrorResponse, useRouteError } from "react-router";

export function Crash() {
  const error = useRouteError();

  return (
    <div className="crash">
      <div className="crash__box">
        <h1 className="crash__title">{title(error)}</h1>
        <p className="crash__detail">{detail(error)}</p>
      </div>
    </div>
  );
}

function title(error: unknown): string {
  if (isRouteErrorResponse(error)) {
    return `${error.status} ${error.statusText}`;
  }
  return "unhandled error";
}

function detail(error: unknown): string {
  if (isRouteErrorResponse(error)) {
    return error.status === 404
      ? "No screen answers that URL. The rail on the left lists everything this build serves."
      : String(error.data);
  }
  if (error instanceof Error) {
    return error.stack ?? error.message;
  }
  return String(error);
}
