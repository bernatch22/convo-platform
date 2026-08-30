# ms-5 — one worker, two businesses

**Landed 2026-08-30 · 4 cards (2 by the orchestrator, 2 by Opus workers) · lands on master with this milestone**

## What we set out to do

Prove the thesis of the whole platform with the cheapest possible experiment:
a second business, with a different register, different systems and a
different irreversible action, served by the *same* worker and the *same*
evaluation machinery — and a router that decides who a call is for from what
the dispatcher, the SIP trunk or the console says, never from the code.

## What we achieved

- **`TENANT=tienda-sur PROJECT=pedidos python worker.py console --text`** is
  a shop: it finds an order by number and phone, reads its status from the
  system, cancels it only after a spoken yes (`cancel_order` is irreversible,
  behind the same `ConfirmTask` and token as the clinic's `book_slot`), refuses
  to cancel a shipped order and offers the return policy instead, and speaks
  "tú" throughout — where the clinic speaks "usted". Same core, same stages
  pattern, same saga, same log.
- **The router reads four sources in order** — dispatch metadata, `convo.*`
  dispatch attributes, the SIP trunk number through the `routes` table, the
  environment — and the first that names a tenant wins. Channel travels with
  the session. An unknown tenant is refused with the known list; a tenant
  whose `tenant.py` raises is simply absent from the registry (proven by
  dropping a broken folder into `tenants/` during a test).
- **Prompts are hybrid.** Git carries the knowledge seed
  (`Project.knowledge_seed`); a row in `project_versions` overrides it without
  a deploy (`python -m convo versions pin`); the version the session ran with
  is in its first log event. A price change is a Tuesday edit, not a release.
- **The evaluation layer became platform code.** Building the shop's metrics
  forced the generic halves out of the clinic: `core/testing/dag.py`
  (`DeterministicNode`, `consent_graph`, `grounded_facts_graph`),
  `core/testing/grounding.py` (extractors, normalisation, evidence) and
  `core/testing/register.py` (a deterministic usted/tú node, 0 judge calls).
  The clinic's `evals/dag.py` went from 265 lines to 81. A tenant now owns
  only its tool names, its criteria wording, its vocabulary and its knowledge.
- **Scores:** shop goldens 20/20 (grounded + register + tool correctness +
  tone), shop consent DAG 3/3 simulated calls at 1.0, clinic consent 5/5 after
  the lift, cross-tenant leakage 1.0 on both directions (see the last card),
  217 unit tests. Milestone spend ≈ $0.55.

## What we learned the hard way

1. **There is no `--tenant` flag.** LiveKit's `cli.run_app` is a click app
   that refuses unknown options; the console chooses with `TENANT` /
   `PROJECT` in the environment. The plan said `--tenant`; the README says
   the truth.
2. **Evidence needs two scopes.** The shop's sheet names every carrier it
   works with, so "lo lleva MRW" about a parcel SEUR is carrying was grounded
   by the sheet. Order numbers, tracking codes and carriers now match against
   the *call* (tool outputs + what the customer said); prices and opening hours
   still match against the sheet.
3. **A summary carries identity, not state.** Handed the whole order row in
   Identify's summary, the model answered "¿por dónde va?" from that note
   instead of reading the system — right today, stale the first time a
   warehouse is quicker than a conversation. Identify hands on the number and
   the name; OrderDesk reads the status itself.
4. **A generic CLI cannot speak one tenant's vocabulary.** `convo sessions
   eval` called `never_book_before_yes()` on any project and would have raised
   on the first shop call. Both projects answer to `consent_policy()`.
5. **The lift exposed a pre-existing clinic defect.** "¿qué turnos hay el
   jueves?" is answered without consulting the agenda when the patient's
   current appointment is on a Thursday. Reproduced on the merge commit before
   the lift; it belongs to the prompt-hardening card (`tk-ff61b4`).
6. **Four judge misreadings, fixed once each and written into the
   criteria:** the platform-rendered confirmation question read as the agent
   "jumping the gun"; a disjunction read as an exclusive or — twice, in both
   tenants' criteria ("either alone is enough, and both is also correct");
   and a tone judge, free to grade the *decision*, read "no, espera, mejor lo
   dejo" backwards and scored a correct refusal 0.2. A judge scores whatever it
   is not explicitly forbidden to score.
7. **CI can skip a whole ring without a word.** `jobs.<id>.if` cannot read
   `secrets`; the expression was false on every run. Guard per step.

## Decisions

- **`dates.py` is deliberately duplicated** between the tenants. One tenant
  importing another would tie two customers' deploys together; a small
  Spanish formatting package upstream would delete both, but that is a
  contribution, not a shortcut.
- **The simulated caller is one class with two lines changed** in both
  tenants — a real lift into `core.testing`, done in its own card
  (`tk-bcd40d`) rather than smuggled in here.
- **Register is a deterministic node, not a judge.** Whole-word matching on
  flattened text; the tuteo that flipped a GEval in ms-3 now scores 0.0 for
  free.

- **A stranger can add a tenant in ten minutes.** `tenants/_template/` has
  the real shape (tenant, adapters, project, knowledge, prompts, stages, tools,
  evals) with `TODO(copy)` at every decision and a README that is the
  walkthrough; `tests/test_template.py` performs that copy on disk, routes a
  fake job to it, renders its prompts and runs its register scan, then
  removes it. `docs/tenants.md` says what a tenant owns (words) and what the
  platform owns (shapes).
- **The tenants stay apart, measured.** `core/testing/leakage.py`: a
  deterministic scan for the *other* tenant's proper nouns, then one binary
  judge on whether the refusal was honest. Tienda Sur asked for a
  traumatología appointment: "Esto es Tienda Sur, una tienda de ropa online…
  ¿algo con un pedido?" — 1.0. Clínica Norte asked where a parcel is: "yo solo
  gestiono las citas médicas" — 1.0. The word lists carry no bare surnames on
  purpose (the shop has a Marta Alonso Gil, the clinic a Dr. Ramón Gil).
- **CI was not running the eval ring.** The `evals` job guarded on
  `secrets.ANTHROPIC_API_KEY` at job level, a context GitHub does not provide
  there, so every run skipped it silently. The guard is per step now; one
  command collects both tenants and the leakage pair.

## Where we stand

Master carries two businesses on one worker, a router that decides from what
the dispatcher or the trunk says, hybrid prompts with the version in the log,
and an evaluation layer that is platform code: consent, grounding, register
and leakage are graphs any tenant instantiates with its own words. 217 unit
tests; 38 DeepEval cases green in one command, ≈ $0.08 a run.

Try it:

```bash
TENANT=tienda-sur PROJECT=pedidos uv run python worker.py console --text
#   > hola, quería saber por dónde va mi pedido   → asks the TS number
#   > es el TS-10432                               → status from the system
#   > quiero cancelarlo                            → "¿Lo cancelo?" → sí → cancelled + SMS
#   (TS-10433 is already shipped: refused, return policy offered)
TENANT=clinica-norte PROJECT=reagendamiento uv run python worker.py console --text
uv run python -m convo routes add cc +34910000000 clinica-norte reagendamiento
uv run python -m convo versions pin clinica-norte reagendamiento v2 ficha.txt
uv run pytest -m unit -q                     # 217 passed
uv run deepeval test run tests/evals -n 3    # both tenants + leakage
```

Read it:

```bash
nvim -p core/router.py core/state/store/protocol.py core/state/store/sqlite.py core/testing/fake_job.py docs/prompts.md
nvim -p tenants/tienda-sur/tenant.py tenants/tienda-sur/adapters/orders.py tenants/tienda-sur/projects/pedidos/stages/order_desk.py tenants/tienda-sur/projects/pedidos/tools.py
nvim -p core/testing/dag.py core/testing/grounding.py core/testing/register.py core/testing/leakage.py tenants/_template/README.md docs/tenants.md
```

Transcripts of both businesses and the leakage pair: `tmp/reports/ms-5.html`.

## What comes next

**ms-6** — talk to the agent from the laptop microphone. Soniox with its
semantic endpointing, ElevenLabs Carolina, Silero VAD and the local turn
detector are already wired on the milestone branch and boot in `console`;
what lands with the milestone is barge-in tuned for Spanish backchannels,
`stt.final` / `tts.word` events with times in the log, `--record` leaving the
stereo OGG referenced from `session.end`, and the first offline voice evals.
