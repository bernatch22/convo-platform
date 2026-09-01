# presentation/ — the deck, and the document it prints to

Fourteen slides that answer the thirteen ABAI *entregables*. The deck on screen
and the PDF are the same source and the same pixels, because the deliverable is
both: something to walk through in front of someone, and a file to send.

**The contract for writing a slide is [`MANIFEST.md`](MANIFEST.md).** Read that
first. This file is only about the machinery.

```bash
npm run serve     # http://127.0.0.1:4630 — reassembled on every request
npm run build     # dist/deck.html — ONE self-contained file
npm run check     # does every slide still fit its 900px page?
npm run pdf       # check, then dist/deck.pdf — 14 pages of 1600×900
```

No dependencies. `npm install` has nothing to install.

## How it fits together

| file | what it is |
|---|---|
| `slides/NN-name.html` | one slide, one file: a bare `<section class="slide" data-title="…">`. Five people write these in parallel and their work never meets in the same diff |
| `build.mjs` | reads the fragments in number order, stamps the index and the printed footer on each, inlines `deck.css`, `deck.js` and every referenced screenshot as a data URI, writes `dist/deck.html` |
| `deck.css` | the visual identity and the chassis — and the writer's whole kit of classes |
| `deck.js` | which slide is showing. Arrows, space, Home/End, `f` for fullscreen, the hash as the state. Plus the `?audit` branch |
| `serve.mjs` | rebuilds on every request and serves the result, so the browser can never show something `npm run build` would not write |
| `audit.mjs` | drives a headless Chromium to ask the deck whether any slide overflows |
| `pdf.mjs` | `dist/deck.html` → `dist/deck.pdf` with `--print-to-pdf` |
| `screenshots/` | evidence captured from the deployed console. Its README has the convention and the exact capture command |
| `stage/` | **parked.** The `@pinecall/stage` voice runtime — the elements that let a page speak with a live agent's mouth. Out of the critical path for this deck by decision: the deliverable is a document and a walkthrough, and a narrator in the critical path makes both hostage to a network. Kept because narrating this deck is still a card |

## Three decisions worth knowing before you change anything

**One self-contained file.** No font CDN, no external CSS, no `<img src>` that
resolves over the network. System font stacks, inlined everything. `deck.html`
has to open from a USB stick and print identically on a machine that has never
seen this repo.

**A slide is exactly 1600×900.** On screen the stage is scaled to fit the
viewport; in print `@page { size: 1600px 900px; margin: 0 }` renders it at
natural size. That is why the PDF is not an approximation of the deck — it is the
deck. It is also why 900px is a hard ceiling, and why `npm run check` exists:
overflow is invisible in a browser and becomes either a cropped slide or a silent
fifteenth page.

**No runtime beyond `deck.js`.** Diagrams are hand-written inline SVG. No
mermaid, no chart library, no framework. A deck that needs to boot something is a
deck that fails in front of somebody.

## Chromium

`audit.mjs` and `pdf.mjs` need a Chromium and find one themselves: `$CHROME`
first, then Playwright's cache (`~/.cache/ms-playwright/chromium*`), then Google
Chrome and the usual Linux paths. Nothing is downloaded. If none is found, the
error lists every path it tried.
