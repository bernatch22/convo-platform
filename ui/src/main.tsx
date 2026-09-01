import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import { router } from "./router";
import "./styles/tokens.css";
import "./styles/app.css";
import "./styles/pipeline.css";
import "./styles/sessions.css";
import "./styles/board.css";
import "./styles/evals.css";

const host = document.getElementById("root");
if (!host) {
  throw new Error("index.html is missing #root");
}

createRoot(host).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
