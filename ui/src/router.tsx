/* Every screen this instrument has, and the one loader that feeds the switcher.
 *
 * The URL is the state: switching tenant or project is a navigation, not a
 * store write, so a screen is always shareable and the back button always
 * means what it says.
 */

import { createBrowserRouter } from "react-router";

import { Crash } from "./routes/Crash";
import { Evals, evalsLoader } from "./routes/Evals";
import { Home } from "./routes/Home";
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
      { path: "t/:tenant/sessions", element: <Sessions />, loader: sessionsLoader },
      { path: "t/:tenant/sessions/:id", element: <SessionDetail />, loader: sessionDetailLoader },
      { path: "t/:tenant/pipeline", element: <Pipeline />, loader: pipelineLoader },
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
