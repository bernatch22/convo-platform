/* Does every slide still fit on its page?
 *
 * 900px is a hard ceiling: a slide taller than that is not warned about
 * anywhere — it is cropped in the browser and silently becomes a second page in
 * the PDF. Five people writing fragments in parallel will hit it, so the deck
 * measures itself: deck.js in `?audit` mode reports each slide's real height
 * through document.title, which is the one value `--dump-dom` hands back
 * without a devtools client.
 *
 *   node audit.mjs        → a table; exit 1 if anything overflows
 */

import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { build } from "./build.mjs";
import { findChrome } from "./pdf.mjs";

const run = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));


/** Measure the built deck. Returns one row per slide, tallest first. */
export async function audit() {
  const { out } = await build();
  const chrome = await findChrome();
  const { stdout } = await run(chrome, [
    "--headless",
    "--disable-gpu",
    "--window-size=1600,900",
    "--virtual-time-budget=4000",
    "--dump-dom",
    `file://${out}?audit`,
  ], { maxBuffer: 1 << 26 });

  const m = stdout.match(/<title>AUDIT:(\[.*?\])<\/title>/s);
  if (!m) throw new Error("the deck did not report — is the ?audit branch still in deck.js?");
  return JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, "&"));
}


if (import.meta.url === `file://${process.argv[1]}`) {
  const rows = await audit();
  const TOLERANCE = 4; // sub-pixel line-height rounding, not a layout problem
  const bad = rows.filter((r) => r.over > TOLERANCE);
  for (const r of rows) {
    const flag = r.over > 4 ? `OVERFLOW +${r.over}px (${r.where})` : "ok";
    console.log(`  ${String(r.n).padStart(2, "0")}  ${String(r.height).padStart(4)}px  ${flag.padEnd(34)}  ${r.title}`);
  }
  if (bad.length) {
    console.error(`\n${bad.length} slide(s) taller than the 900px page: ${bad.map((r) => r.n).join(", ")}.`);
    console.error("They will be cropped on screen and split across two PDF pages. Cut content.");
    process.exit(1);
  }
  console.log("\nall 14 slides fit the page");
}
