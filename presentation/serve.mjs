/* The dev server: rebuild on every request, serve the one file.
 *
 * There is deliberately no watcher and no cache. Reassembling fourteen
 * fragments costs a few milliseconds, and rebuilding per request means what
 * you see in the browser is byte-for-byte what `npm run build` writes — the
 * demo and the deliverable can never drift.
 *
 *   node serve.mjs        → http://127.0.0.1:4630
 */

import { createServer } from "node:http";
import { build } from "./build.mjs";

const PORT = Number(process.env.PORT || 4630);

createServer(async (req, res) => {
  try {
    const { html, count } = await build({ write: false });
    res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
    res.end(html);
    console.log(`${req.method} ${req.url} · ${count} slides`);
  } catch (err) {
    res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    res.end(String(err && err.stack ? err.stack : err));
    console.error(err);
  }
}).listen(PORT, "127.0.0.1", () => {
  console.log(`presentation → http://127.0.0.1:${PORT}`);
});
