/* Every screen this instrument has, and the one loader that feeds the switcher.
 *
 * The URL is the state: switching tenant or project is a navigation, not a
 * store write, so a screen is always shareable and the back button always
 * means what it says.
 */

import { createBrowserRouter } from "react-router";

import { Crash } from "./routes/Crash";
import { Evals } from "./routes/Evals";
import { Home } from "./routes/Home";
import { Pipeline } from "./routes/Pipeline";
import { SessionDetail } from "./routes/SessionDetail";
import { Sessions } from "./routes/Sessions";
import { Shell, shellLoader } from "./routes/Shell";
import { Supervisor } from "./routes/Supervisor";
import { Talk } from "./routes/Talk";

export const router = createBrowserRouter([
  {
    id: "root",
    path: "/",
    element: <Shell />,
    loader: shellLoader,
    errorElement: <Crash />,
    children: [
      { index: true, element: <Home /> },
      { path: "t/:tenant/sessions", element: <Sessions /> },
      { path: "t/:tenant/sessions/:id", element: <SessionDetail /> },
      { path: "t/:tenant/pipeline", element: <Pipeline /> },
      { path: "t/:tenant/:project", element: <Talk /> },
      { path: "evals", element: <Evals /> },
      { path: "supervisor", element: <Supervisor /> },
    ],
  },
]);
