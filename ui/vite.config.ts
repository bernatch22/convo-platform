import { execSync } from "node:child_process";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** The control plane the dev server proxies to; every API path below is forwarded there. */
const API = process.env.CONVO_API ?? "http://127.0.0.1:8090";

const API_PATHS = ["/tenants", "/token", "/observe", "/sessions", "/live-calls", "/pipeline"];

function gitSha(): string {
  try {
    return execSync("git rev-parse --short HEAD", { encoding: "utf8" }).trim();
  } catch {
    return "nogit";
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  define: {
    __GIT_SHA__: JSON.stringify(gitSha()),
    __ENVIRONMENT__: JSON.stringify(process.env.CONVO_ENV ?? mode),
  },
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      API_PATHS.map((path) => [path, { target: API, changeOrigin: true }]),
    ),
  },
  build: { outDir: "dist", sourcemap: true },
}));
