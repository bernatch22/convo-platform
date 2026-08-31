/* dist/deck.html → dist/deck.pdf, one slide per page, offline.
 *
 * No puppeteer and no playwright dependency: we drive whatever Chromium the
 * machine already has with --print-to-pdf. The page size comes from the deck's
 * own `@page { size: 1600px 900px }`, so a PDF page IS a slide at the pixels it
 * was designed at — no scaling, no margins, no header/footer from the browser.
 *
 *   node pdf.mjs          → dist/deck.pdf
 */

import { execFile } from "node:child_process";
import { access, readdir, mkdir } from "node:fs/promises";
import { constants } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { homedir } from "node:os";

import { build } from "./build.mjs";

const run = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(HERE, "dist");
const PDF = join(OUT_DIR, "deck.pdf");


/** The first Chromium on this machine, or an error naming every place we looked. */
export async function findChrome() {
  const tried = [];
  const candidates = [];

  if (process.env.CHROME) candidates.push(process.env.CHROME);

  // Playwright's cache, if anything in this repo ever ran `playwright install`.
  const cache = join(homedir(), ".cache", "ms-playwright");
  try {
    for (const dir of await readdir(cache)) {
      if (!dir.startsWith("chromium")) continue;
      for (const inner of await readdir(join(cache, dir))) {
        candidates.push(join(cache, dir, inner, "chrome-headless-shell"));
        candidates.push(join(cache, dir, inner, "Chromium.app", "Contents", "MacOS", "Chromium"));
        candidates.push(join(cache, dir, inner, "chrome"));
      }
    }
  } catch { /* no cache; fine */ }

  candidates.push(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  );

  for (const path of candidates) {
    tried.push(path);
    try {
      await access(path, constants.X_OK);
      return path;
    } catch { /* next */ }
  }
  throw new Error(
    "no Chromium found. Set CHROME=/path/to/chrome, or install one. Looked at:\n  " + tried.join("\n  "),
  );
}


async function main() {
  const { out, count } = await build();
  await mkdir(OUT_DIR, { recursive: true });
  const chrome = await findChrome();

  await run(chrome, [
    "--headless",
    "--disable-gpu",
    "--no-pdf-header-footer",
    "--run-all-compositor-stages-before-draw",
    "--virtual-time-budget=6000",
    `--print-to-pdf=${PDF}`,
    `file://${out}`,
  ], { maxBuffer: 1 << 24 });

  console.log(`deck.pdf · ${count} pages → ${PDF}`);
  console.log(`  rendered by ${chrome}`);
}

/* Only when run directly: audit.mjs imports findChrome from here, and an
 * import that prints a PDF as a side effect is a trap. */
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
