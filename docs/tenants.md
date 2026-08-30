# Tenants — what a business owns, and what the platform owns

One deploy, many businesses. `tenants/clinica-norte/` speaks to patients as
*usted* and moves appointments; `tenants/tienda-sur/` tutea and cancels orders;
they run in the same worker, on the same registry, router, session, executor and
event log. **No file under `core/` names either of them** — the registry finds
tenants by folder and imports each one by name, in a try/except, so a tenant
that fails to import is unroutable rather than fatal
(`tests/test_router.py::test_a_broken_tenant_folder_is_unroutable...`).

New business? Copy `tenants/_template/` and follow its README — it is a working
tenant with a ten-minute walkthrough, and `tests/test_template.py` proves the
copy routes, declares tools its adapters can serve, renders its prompts and
scans its own register.

## The line

| layer | the platform owns (`core/`, `worker.py`, `api.py`) | the tenant owns (`tenants/<id>/`) |
|---|---|---|
| **identity** | resolving a job into one `TenantContext` (metadata → attributes → dialled number → env), the registry, the fleet | its id, name and region; which projects it exposes |
| **systems** | the `Adapter` protocol, the executor that picks an adapter by capability, timeouts, retries, masking | one adapter per system it runs, and what each `capability` returns |
| **tools** | the `ToolSpec` contract, the catalog lookup, the guard, the saga and its compensation, the failure taxonomy | which tools exist, each one's `side_effect`, `idempotency_key`, `compensation`, `timeout_s` and `pii_scope`; the tool docstrings the model reads |
| **conversation** | `TenantAgent`, handoffs, the summary that travels, `ConfirmTask`, turn detection, STT/TTS/LLM wiring | the stages, their prompts, the voice, the language, the register (*usted* or *tú*) |
| **knowledge** | the seed/override rule and the version pinned into every session (`docs/prompts.md`) | the knowledge block itself — over 4096 tokens, dateless, id-free |
| **words on failure** | the four failure kinds (`UNKNOWN_TOOL`, `NO_ADAPTER`, `TIMEOUT`, `FAILURE`) and when each is said | what each of them sounds like in this business's voice (`Project.messages`) |
| **state** | the append-only event log, the per-session `seq`, the session report, re-engagement | nothing: a tenant never writes to the log directly |
| **evals** | the metric *shapes* — consent, grounded facts, register, leakage (`core/testing/`) — the harness, the bridge, the report | its goldens, its metrics module, its thresholds, its extractors, the criteria wording, the register and neighbour word lists |
| **routing** | `routes` and `project_versions` in the store, the dispatch rules, the numbers | nothing: a phone number is a route the platform holds, never a project constant |

The rule behind the table: **the platform owns shapes, a tenant owns words.**
When a project finds itself writing a graph node, a retry loop or a router
branch, the shape is missing from `core/` and belongs there — with the words
left behind in the tenant. Ms-5 is that lift: `dag.py` in both demo tenants is
~70 lines of constants and four one-line factories, and the two read as
translations of each other.

## The two directions it can break

- **A tenant reaching into the platform.** A project that imports
  `livekit.agents` directly, writes to the log, or hardcodes a phone number
  breaks on the next release. Projects import `core.agents`, and
  `tests/test_core_isolation.py` enforces the other direction.
- **The platform learning a tenant.** A branch in `core/` that says
  `if tenant.id == "clinica-norte"` is the moment the platform stops being
  multi-tenant. The check is a metric, not a code review: `no_leakage()` asks
  each business for what only the other one does
  (`tests/evals/test_leakage_deepeval.py`), the deterministic half being a scan
  for the neighbour's proper nouns and the judge half being whether the refusal
  was honest.

## Where a tenant is named

Four places, in the order `core/router.py` reads them, and nowhere else:

1. `ctx.job.metadata` — a dispatch's JSON (`SessionMeta`).
2. `ctx.job.attributes` — `convo.tenant` / `convo.project` / `convo.channel`.
3. the dialled number, looked up in `routes` for this fleet.
4. `TENANT` / `PROJECT` in the environment — the console's way in:

```bash
TENANT=clinica-norte PROJECT=reagendamiento uv run python worker.py console --text
TENANT=tienda-sur    PROJECT=pedidos        uv run python worker.py console --text
```

The **channel** (voice or chat) belongs to the session, not to the project: the
same project answers a phone call and a web chat, and only the session says
which one this is.
