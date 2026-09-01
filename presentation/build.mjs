/* Assemble slides/NN-name.html into ONE self-contained dist/deck.html.
 *
 * Why one file: the deck is also the document ABAI asked for. It has to open
 * from a USB stick with no server, no network and no font CDN, and it has to
 * print to a PDF that looks like what was on screen. So the CSS, the runtime
 * and every screenshot are inlined, and the fonts are system stacks.
 *
 * Why fragments: five people write slides in parallel. One file per slide means
 * their work never meets in the same diff, and a slide nobody wrote still
 * assembles — it just wears its placeholder in public.
 *
 *   node build.mjs            → dist/deck.html
 */

import { readFile, readdir, writeFile, mkdir } from "node:fs/promises";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(HERE, "dist");
const OUT = join(OUT_DIR, "deck.html");

const DECK_TITLE = "Plataforma conversacional transaccional — arquitectura";
const DECK_BRAND = "convo · plataforma conversacional transaccional";

const MIME = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp" };


/** Build the deck and write it. Returns the HTML, so serve.mjs can reuse it. */
export async function build({ write = true } = {}) {
  const fragments = await readFragments();
  const css = await readFile(join(HERE, "deck.css"), "utf8");
  const js = await readFile(join(HERE, "deck.js"), "utf8");

  const sections = [];
  for (const [n, frag] of fragments.entries()) {
    sections.push(await inlineAssets(decorate(frag, n, fragments.length)));
  }

  const html = page({ css, js, body: sections.join("\n\n") });
  if (write) {
    await mkdir(OUT_DIR, { recursive: true });
    await writeFile(OUT, html, "utf8");
  }
  return { html, count: fragments.length, out: OUT, titles: fragments.map((f) => f.title) };
}


/** Every slides/NN-*.html in number order, with the title read off its tag. */
async function readFragments() {
  const dir = join(HERE, "slides");
  const names = (await readdir(dir)).filter((n) => n.endsWith(".html")).sort();
  const out = [];
  for (const name of names) {
    const raw = (await readFile(join(dir, name), "utf8")).trim();
    if (!raw.startsWith("<section")) {
      throw new Error(`slides/${name} must start with <section class="slide" data-title="…">`);
    }
    out.push({ name, raw, title: attr(raw, "data-title") || name.replace(/\.html$/, "") });
  }
  if (!out.length) throw new Error("no fragments in slides/ — nothing to assemble");
  return out;
}


/** Stamp the index and the printed footer onto one fragment. */
function decorate(frag, n, total) {
  const num = String(n + 1).padStart(2, "0");
  const foot =
    `\n  <footer class="slide-foot">` +
    `<span class="brand">${DECK_BRAND}</span>` +
    `<span class="num">${num} / ${String(total).padStart(2, "0")}</span>` +
    `</footer>\n`;
  return frag.raw
    .replace(/^<section/, `<section data-idx="${n}"`)
    .replace(/<\/section>\s*$/, `${foot}</section>`);
}


/** Turn every local <img src="screenshots/…"> into a data URI. */
async function inlineAssets(html) {
  const refs = [...html.matchAll(/src="((?:screenshots|assets)\/[^"]+)"/g)].map((m) => m[1]);
  let out = html;
  for (const ref of new Set(refs)) {
    let bytes;
    try {
      bytes = await readFile(join(HERE, ref));
    } catch {
      throw new Error(`a slide points at ${ref}, which does not exist — capture it or use the .shot-missing placeholder`);
    }
    const mime = MIME[extname(ref).toLowerCase()] || "application/octet-stream";
    out = out.split(`src="${ref}"`).join(`src="data:${mime};base64,${bytes.toString("base64")}"`);
  }
  return out;
}


/** Read one attribute off an opening tag, without pulling in a parser. */
function attr(html, name) {
  const m = html.match(new RegExp(`${name}="([^"]*)"`));
  return m ? m[1] : null;
}


function page({ css, js, body }) {
  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${DECK_TITLE}</title>
<style>
${css}
</style>
</head>
<body>
<div class="deck">
  <div class="stage" id="stage">

${body}

  </div>
</div>
<div class="chrome">
  <div class="progress"></div>
  <nav class="dots" aria-label="slides"></nav>
  <div class="hint">← → · espacio · inicio/fin · f pantalla completa</div>
</div>
<script>
${js}
</script>
</body>
</html>
`;
}


if (import.meta.url === `file://${process.argv[1]}`) {
  const { count, out, titles } = await build();
  console.log(`deck.html · ${count} slides → ${out}`);
  titles.forEach((t, n) => console.log(`  ${String(n + 1).padStart(2, "0")}  ${t}`));
}
