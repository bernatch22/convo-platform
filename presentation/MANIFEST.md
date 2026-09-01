# MANIFEST — the deck's contract

Fourteen slides, written by five people who never see each other's work until it
assembles. This file is what makes that safe: it fixes the number, the title,
the ABAI *entregable* each slide answers, what has to be on it and what carries
the evidence. **Read it before writing a fragment; do not renumber, retitle or
add a slide without changing this file first.**

---

## 1. What the deck has to be

The ABAI exercise asks for a technical design covering thirteen *entregables*,
**in at most 15 slides**, with **at least one architecture diagram** and **at
least one sequence diagram**. We use 14: thirteen answers plus the slide that
states the criteria the other thirteen are judged by.

The deck is also the document. `npm run build` produces one self-contained
`deck.html` (no server, no network, no font CDN) and `npm run pdf` prints it at
1600×900 per page. What is on screen is what is in the PDF, pixel for pixel —
so nothing may depend on hover, animation or a live connection.

**Weighting.** Orchestration, multi-tenancy, security and infrastructure get the
depth; chat and the choice of LLM get a line each. That is where the exercise is
actually decided, and it is where this platform has the most to show.

---

## 2. The voice

Every slide is one argument in three moves. In this order, always:

1. **Decisión** — what we chose, stated in the affirmative and in the present.
   Not "se podría", not "se recomienda". *"El consentimiento es un paso de la
   saga, no una frase del prompt."*
2. **Justificación** — the constraint that forced it, and what the alternative
   would have cost. One or two sentences. Name the alternative; a decision with
   no rejected option is not a decision.
3. **Línea de validación empírica** — the `.proof` line: a measured number, a
   session id, a `file:línea`, or the command that reproduces it. Every slide
   owes one. A slide with no proof line is not finished.

Register: Spanish, Principal-Architect sober. Impersonal or first person plural,
never second person. No sales register, no exclamation marks, no "potente",
"robusto" or "escalable" unless a number follows.

### The rules that get a fragment rejected

- **No adjective without a number.** "Barato" is not a claim; `0.0063 €` is.
- **Every claim is falsifiable** — it names a file, a command, a session, a
  metric or a commit. If nobody can check it, cut it.
- **~110 words of prose maximum** on a slide. Everything else is structure:
  rows, tables, a diagram, a screenshot. If it needs more prose, it is a
  REPORT.md section, not a slide.
- **The screenshot is evidence, not decoration.** If the slide reads the same
  without it, drop the image.
- **Say what we did NOT build**, on the slides where that is the interesting
  half. Trade-offs are the thirteenth entregable; they are not an apology.
- **No `lorem`, no "TODO" left in a fragment.** An unwritten slide keeps its
  `.todo` block, which is loud on purpose.

---

## 3. How to write a fragment

One file, `slides/NN-nombre.html`, and it *is* a `<section>`:

```html
<section class="slide" data-title="Gestión de estado" data-entregable="6">
  <div class="slide-body">
    <div class="head-block" data-anim="1">
      <div class="eyebrow">06 <span class="sep">·</span> Entregable 6 — gestión de estado</div>
      <h2 class="head">La sesión no se reanuda: se re-engancha</h2>
      <p class="lede">…decisión…</p>
    </div>
    …
    <div class="proof" data-anim="4">…</div>
  </div>
</section>
```

`build.mjs` adds `data-idx` and the printed footer. Never write the footer, the
page number or the `<html>` wrapper yourself.

**The kit** (all of it is in `deck.css`, and using anything else means editing
`deck.css`, which is a shared seam — say so on the board first):

| class | for |
|---|---|
| `.eyebrow` | the mono line above the head: slide number · entregable |
| `h1.title` / `h2.head` / `.lede` | the title slide / every other head / the decision paragraph |
| `.proof` | **the validation line — mandatory** |
| `.grid2` `.grid3` `.grid-7-5` `.grid-5-7` | the layouts. `.fill` on the part that should take the rest of the height |
| `.card` (`.label` `.value` `.desc`) | a measured fact in a box |
| `.rows > .row` (`.idx` `.txt` `.txt .why`) | a numbered list with a reason under each line. `style="--row-pad:10px"` on `.rows` tightens it when the column is full |
| `.kv` (`dt`/`dd`) | mono key → prose value |
| `table.plain` | a comparison with real columns |
| `.tag` `.tag.ok` `.tag.warn` `.tag.off` | a small state marker |
| `pre.code` | a contract, a frame, a snippet. Real code only |
| `.compare` (`.when`) | hoy \| mañana side by side — slide 09 exists for this |
| `.fig` + `figcaption`, `.shot`, `.shot-frame` | a diagram or a screenshot with its caption |
| `.shot-missing` | a screenshot that does not exist yet, with the instruction to capture it. It is a flex column, so put the prose in ONE child: `<b>Falta: …</b><div>…</div>` |
| `.note` | the small print under a table |
| `[data-anim="1..7"]` | the entrance order. Print ignores it |
| `svg .box` `.box-accent` `.edge` `.edge-accent` `.lbl` `.lbl-sm` | the diagram primitives, so two authors draw with one hand |

**Diagrams are inline SVG**, hand-written, on a `viewBox` — never an image,
never a library, never mermaid: the deck has no network and no runtime beyond
`deck.js`. Screenshots come from `screenshots/`; read that directory's README
before adding one.

---

## 4. The fourteen slides

Legend: **E-n** = ABAI entregable n. *Card* = the board card that owns it.

---

### 01 · `01-objetivos.html` — Objetivos de diseño
**Answers:** the frame for all thirteen; states the criteria E-13 is judged by.
**Card:** tk-dd6a4a (this one — **written, it is the voice example**).

- The thesis: the LLM is a swappable interface driver; the platform is a process
  runtime that talks. Control, state, tools, audit and tenancy live in the
  backend, never in the prompt.
- The four non-negotiables the rest of the deck keeps referring back to:
  determinism where money moves, tenancy as data, everything auditable by
  construction, cost and latency measured per call.
- What "transaccional" costs: a conversation that books something needs
  confirmation, idempotency and compensation — three mechanisms, not a tone.
- The proof line: the platform is running, and every number in this deck comes
  off a real call.

**Carries:** no figure. This slide is type only — it earns the right to the
diagrams that follow.

---

### 02 · `02-arquitectura.html` — Arquitectura de alto nivel
**Answers:** E-1 (arquitectura de alto nivel). **Card:** tk-14fc29.

- **The architecture diagram** (the one ABAI requires): channels (SIP/PSTN,
  WebRTC, chat) → LiveKit SFU → worker job per call → control plane over HTTP →
  tools, local and remote → customer systems. Show the process boundary: one job
  is one OS process and holds no pool.
- The three planes named and separated: data plane (`worker.py`), control plane
  (`api.py`), evidence plane (the event log and the console).
- Why the LLM sits *inside* one box and not around the diagram — it is one node,
  and it is replaceable.
- What crosses the network and what never does (no DB in the job process; all
  business IO over HTTP).

**Carries:** inline SVG, the full width of the slide. This is the deck's
centrepiece — give it the room and put the prose in three lines beside it.

---

### 03 · `03-dominios.html` — Dominios y bounded contexts
**Answers:** E-2 (dominios / bounded contexts). **Card:** tk-14fc29.

- Seven contexts: Session, Process, Tools & Adapters, Tenancy & Config, Audit,
  Evaluation, Supervision. One line each saying what it owns and what it refuses.
- The dependency rule that keeps them honest: `core/` never imports `tenants/`,
  and a test enforces it (`tests/test_core_isolation.py`).
- Where the seams actually are in the tree, so the reader can open them.
- The one context that is deliberately thin today, and why.

**Carries:** a context map (small SVG) or `.rows`. Not another box diagram —
slide 02 already spent that.

---

### 04 · `04-ejecucion.html` — Ejecución de una conversación
**Answers:** E-3 (modelo de ejecución). **Card:** tk-14fc29.

- **The sequence diagram** (the second one ABAI requires): STT interim → turn
  closed → LLM → tool call → guard → `ConfirmTask` → TTS, with the event log
  written *during* the turn, not after it.
- Turn detection as a decision: who closes a turn, and what happens when the
  caller interrupts.
- Real per-leg latency, from a real call.
- The failure paths on the same diagram: provider error, orphan `tool_use`,
  the call dropping mid-saga.

**Carries:** inline SVG sequence diagram + the latency numbers from
`session-detail.png` (do not paste the screenshot here; slide 12 owns it).
Measured on session `AJ_rdrkYph3FaeS`: ttft 0.64 s (max 1.01), transcription
0.47 s, tts ttfb 0.11 s, e2e 3.31 s.

---

### 05 · `05-tools.html` — Tools y contratos
**Answers:** E-4 (diseño de tools y contratos). **Card:** tk-a66bd0.

- `ToolSpec` in full: `side_effect: read|write|irreversible`, `idempotency_key`,
  `pii_scope`, `timeout_s`, `compensation`. Show the actual dataclass.
- The docstring is the schema the model sees — the contract is read twice, once
  by the guard and once by the LLM.
- `ToolError` vs any other exception: what the model is allowed to learn about a
  failure, and what it must never see.
- Local tool vs adapter vs remote tool: the same contract, three executors.

**Carries:** `pre.code` with the real `ToolSpec`, plus one tool declared beside
it. Two columns.

---

### 06 · `06-orquestacion.html` — Orquestación transaccional
**Answers:** E-5 (orquestación transaccional). **Card:** tk-a66bd0. **Deep slide.**

- Two-phase consent: the model may *ask*, only `ConfirmTask` may *mint* the
  `confirmation_token`, and `guard.check` refuses any `irreversible` tool without
  one. The authority is never in the prompt.
- The saga: steps, compensation, and idempotency keys that survive a retry.
- What happens when the caller hangs up between "sí" and the write.
- The consent proof as a first-class artefact: `seq 39 asked; seq 46 authorised;
  seq 51` on a real call.

**Carries:** `screenshots/session-detail.png` cropped to the CONSENT PROOF block,
or the same evidence typeset. A small state diagram is welcome if it fits.

---

### 07 · `07-estado.html` — Gestión de estado
**Answers:** E-6 (gestión de estado). **Card:** tk-a66bd0.

- The append-only event log with a per-session `seq`, written *during* the call
  so a SIGKILL cannot lose the stage.
- Sessions are **re-engaged, not resumed**: a dropped call is a new room and a
  new job; we snapshot `ChatContext` + stage keyed by the caller's number and
  rehydrate on the next inbound within N minutes. Say why resumption is a lie.
- What is state, what is derived, and what is deliberately not persisted.
- Handoff between stages does not copy history — the summary is rebuilt in
  `on_enter`.

**Carries:** `screenshots/sessions.png` (one row per conversation, with turns,
events and cost) or the log of one session.

---

### 08 · `08-multitenant.html` — Configuración multi-cliente
**Answers:** E-7 (configuración por cliente / proyecto). **Card:** tk-f0aadc. **Deep slide.**

- Tenant is **data**, not a deploy: one fleet, many businesses, routing resolved
  from the dispatch metadata into a single `TenantContext`.
- Code vs configuration: what lives in `tenants/<t>/projects/<p>/` and what lives
  in the control plane's tables — and why voice, models and prompts are the
  second kind.
- Hot overrides: a project changes its pipeline without a deploy, and the console
  shows the pipeline the *next call* will really run.
- Blast radius: a broken tenant is unroutable, it does not take the fleet down
  (`core/registry.py` imports each tenant in try/except).

**Carries:** `screenshots/pipeline.png` — it shows the resolved pipeline with the
allow-list and the model the platform *refuses* to run.

---

### 09 · `09-integraciones.html` — Integraciones y el protocolo remote-tenant
**Answers:** E-8 (integración con sistemas externos). **Card:** tk-f0aadc. **Deep slide.**

- **Hoy:** the tenant is a package in our tree. Adapter ports, the registry, the
  generic REST adapter. Honest about what that costs the customer.
- **Mañana:** the customer's agent runs in *their* process, connected by an
  **outbound** WebSocket — no inbound firewall hole, no webhook to secure. Core
  becomes the runtime that gives it life.
- The frames, written out: `hello` / `register(manifest)` / `invoke` / `result`,
  plus what happens on a disconnect mid-`invoke`.
- Why outbound and not webhooks, in one line about who has to open a port.

**Carries:** the `.compare` block — hoy on the left, mañana on the right, same
row labels. The dropped ms-12 card specs are the input; reuse their frame
definitions rather than inventing new ones.

---

### 10 · `10-handoff.html` — Handoff a un humano
**Answers:** completes E-5 (the human as a step of the orchestration) and feeds
E-10. **Card:** tk-06abff.

- Three capabilities, one ladder: `listen` (hidden, subscribe-only) → `whisper`
  (still hidden, text to the agent over RPC) → `takeover` (a real microphone and
  a participant the caller can see).
- **The authority is a signed, short-lived token**, not a control on a screen.
  The console can only offer what the ticket already allows.
- Every verb is appended to the caller's own session log with its own `seq`, so
  one call stays one story even when two humans touched it.
- What the caller is and is not told, and why that is a product decision.

**Carries:** `screenshots/supervisor.png`.

---

### 11 · `11-seguridad.html` — Seguridad y privacidad
**Answers:** E-10 (seguridad y privacidad). **Card:** tk-06abff. **Deep slide.**

- Write it **in the positive**: what the platform grants, not what it forbids.
  Four properties — PII handled by value and scoped per tool, tenant segregation
  by construction, minimum surface, short-lived tokens.
- The token model end to end: JWT per tenant, room prefix, dispatch metadata,
  the supervisor ticket. One diagram-free table.
- Secrets only from env; what is never written to the log, and how a session can
  be crypto-shredded.
- The one attack we paid for elsewhere and designed against here (SIP/PSTN
  exposure — the trunk accepts the carrier's IPs and nothing else).

**Carries:** a table, no screenshot. `.taskops/reports/security.md` is the
source; cite it.

---

### 12 · `12-observabilidad.html` — Observabilidad, QA y billing
**Answers:** E-9 (observabilidad, auditoría, replay y QA). **Card:** tk-e69363.

- The four rings of evaluation, from unit tests to a judged real call — and
  which of them gates CI.
- **Every call scores itself**: four deterministic checks decided by code plus at
  most one Haiku judgement, written into the same log as `session.score` within a
  minute of hanging up. The judgement cost `0.0018 €` against a `0.0100 €` cap
  proved before the call was made.
- Replay: the log is complete enough to re-run the turns without the audio.
- Billing is the same pipe: cost per call in euros, per session, on the same row
  as the score.

**Carries:** `screenshots/evals.png` (the delta against the previous run) and
`screenshots/session-detail.png` (the five checks). Two figures, one row.

---

### 13 · `13-infraestructura.html` — Infraestructura y despliegue
**Answers:** E-11 (infraestructura cloud y despliegue). **Card:** tk-e69363. **Deep slide.**

- What runs today: self-hosted LiveKit (SFU + SIP), Redis, MinIO, Caddy, the
  workers, the control plane. No GPU anywhere, on purpose — the turn detector is
  a local CPU model.
- Scaling with **named triggers**, not adjectives: what metric moves what knob,
  and at what value.
- CI/CD with the evals as a gate: a prompt change that drops a golden does not
  ship.
- Cost: what one call costs in providers and what one box costs per month.

**Carries:** a deployment diagram (small SVG) or a table of the compose units.

---

### 14 · `14-roadmap.html` — Roadmap por fases y trade-offs
**Answers:** E-12 (roadmap) **and** E-13 (trade-offs). **Card:** tk-dd6a4a
(this one — **written, it is the voice example**).

- The phases are not a plan: they are a log. Sixteen milestones on a public
  board, each ending with a command a human ran.
- What comes next, in order, with the trigger that starts each phase.
- The trade-offs that were **measured**, each with the option rejected and the
  cost of rejecting it: LiveKit vs a managed stack, Haiku vs a bigger model,
  tenant-as-package vs remote-tenant, self-hosting the SFU.
- What we deliberately did not build, and what would have to be true to build it.

**Carries:** `screenshots/board.png` when it exists — until then the
`.shot-missing` placeholder with the capture instruction.

---

## 5. Coverage — the thirteen entregables

| # | Entregable (ABAI's words) | Slide |
|---|---|---|
| 1 | Arquitectura de alto nivel | **02** |
| 2 | Dominios / bounded contexts | **03** |
| 3 | Modelo de ejecución de una conversación | **04** |
| 4 | Diseño de tools y contratos | **05** |
| 5 | Orquestación transaccional | **06** (+ 10) |
| 6 | Gestión de estado | **07** |
| 7 | Configuración por cliente / proyecto | **08** |
| 8 | Integración con sistemas externos | **09** |
| 9 | Observabilidad, auditoría, replay y QA | **12** |
| 10 | Seguridad y privacidad | **11** (+ 10) |
| 11 | Infraestructura cloud y despliegue | **13** |
| 12 | Roadmap por fases | **14** |
| 13 | Trade-offs principales | **14** (criteria set on **01**) |

Required figures: architecture diagram → **02**; sequence diagram → **04**.
Both are mandatory and both belong to card tk-14fc29.

---

## 6. Working on this in parallel

```bash
cd presentation
npm run serve     # http://127.0.0.1:4630 — rebuilt on every request
npm run build     # dist/deck.html, one self-contained file
npm run check     # does every slide still fit its page? exit 1 if not
npm run pdf       # runs check first, then dist/deck.pdf, 14 pages of 1600x900
```

- **Touch only your own fragments.** `deck.css`, `deck.js`, `build.mjs` and this
  file are shared seams: if your slide needs a new class, say so on the board
  before editing `deck.css`, or the next merge eats it.
- `npm run build` must stay green with unwritten fragments. It will refuse a
  fragment that does not start with `<section class="slide" data-title="…">`,
  and it will refuse a slide pointing at a screenshot that does not exist.
- **900px is a hard ceiling and the deck enforces it.** `npm run check` measures
  every slide in a headless browser and fails on two things a browser never warns
  about: a slide taller than its page (which becomes a silent extra PDF page) and
  a flex/grid track whose content spills and quietly sits on top of what is under
  it. `npm run pdf` refuses to print until it passes. When it fails it names the
  slide, the overflow in pixels and the box that caused it — cut content, do not
  raise the ceiling.

## 7. What a stranger could reuse

`build.mjs`, `serve.mjs`, `pdf.mjs`, `audit.mjs` and `deck.js` are ~400 lines
with no dependencies and nothing about this project in them: fragments in, one
self-contained HTML file and a PDF out, driven by whatever Chromium is already on
the machine. The piece worth stealing is `audit.mjs`: a layout assertion with no
devtools client and no Playwright — the page measures itself and answers through
`document.title`, which `chrome --headless --dump-dom` hands back. Lift the five
files, replace `deck.css`, and it is a deck engine for anything.

What would need work upstream rather than here: `--watch` instead of rebuilding
per request, and a real CDP client so the audit can report more than one value
without smuggling it through the title.
