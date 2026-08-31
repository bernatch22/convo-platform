/* Every screen this instrument has, and the one loader that feeds the switcher.
 *
 * The URL is the state: switching tenant or project is a navigation, not a
 * store write, so a screen is always shareable and the back button always
 * means what it says.
 *
 * Every working screen is scoped to a project — `/t/<tenant>/<project>` is
 * Talk, and Sessions and Pipeline hang one segment below it. Sections used to
 * be tenant-scoped, which left the rail unable to say which project you were
 * configuring and left Pipeline guessing one; the old shapes now redirect
 * (see `routes/legacy.ts`), so bookmarks keep working.
 */

import { createBrowserRouter } from "react-router";

import { Board, boardLoader } from "./routes/Board";
import { Crash } from "./routes/Crash";
import { Evals, evalsLoader } from "./routes/Evals";
import { Home } from "./routes/Home";
import {
  legacyPipelineLoader,
  legacySessionDetailLoader,
  legacySessionsLoader,
  legacyTenantLoader,
} from "./routes/legacy";
import { Pipeline, pipelineLoader } from "./routes/Pipeline";
import { SessionDetail, sessionDetailLoader } from "./routes/SessionDetail";
import { Sessions, sessionsLoader } from "./routes/Sessions";
import { Shell, shellLoader } from "./routes/Shell";
import { Supervisor } from "./routes/Supervisor";

export const router = createBrowserRouter([
  {
    id: "root",
    path: "/",
    element: <Shell />,
    loader: shellLoader,
    errorElement: <Crash />,
    children: [
      { index: true, element: <Home /> },

      // The URLs from before sections were project-scoped. They only redirect.
      { path: "t/:tenant", loader: legacyTenantLoader },
      { path: "t/:tenant/sessions", loader: legacySessionsLoader },
      { path: "t/:tenant/sessions/:id", loader: legacySessionDetailLoader },
      { path: "t/:tenant/pipeline", loader: legacyPipelineLoader },

      { path: "t/:tenant/:project/sessions", element: <Sessions />, loader: sessionsLoader },
      {
        path: "t/:tenant/:project/sessions/:id",
        element: <SessionDetail />,
        loader: sessionDetailLoader,
      },
      { path: "t/:tenant/:project/board", element: <Board />, loader: boardLoader },
      { path: "t/:tenant/:project/pipeline", element: <Pipeline />, loader: pipelineLoader },
      {
        // The only screen that needs the SFU client, so it is the only one that downloads
        // it: livekit-client is half the bundle and no other screen touches a room.
        path: "t/:tenant/:project",
        lazy: async () => ({ Component: (await import("./routes/Talk")).Talk }),
      },

      { path: "evals", element: <Evals />, loader: evalsLoader },
      { path: "supervisor", element: <Supervisor /> },
    ],
  },
]);
