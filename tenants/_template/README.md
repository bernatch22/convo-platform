# Tenant template — a new business on this platform in ten minutes

This folder is a working tenant. It imports, it routes, it runs a call and it
has its own evals; the only thing wrong with it is that the business is made up.
Copy it, rename it, replace every `TODO(copy)`, and you have a second business
running on the same convo.worker as the first — with no change anywhere in `convo/`.

The two demo tenants next door are the same shape, filled in:
`tenants/clinica-norte/` (a clinic, speaks *usted*) and `tenants/tienda-sur/`
(a shop, tutea). When a TODO here is not enough, open the same file over there.

## 1. Copy and rename (2 minutes)

```bash
cp -r tenants/_template tenants/<your-id>
grep -rl 'example-co' tenants/<your-id> | xargs sed -i '' 's/example-co/<your-id>/g'
```

`<your-id>` is the folder name **and** the string that reaches this tenant: a
dispatch's metadata, a row in `routes`, or `TENANT=` on the console. Nothing
else may name it — the registry discovers tenants by folder, and `convo/` never
imports one. Rename `projects/example/` too if your use case has a better name,
and change `PROJECT.id` with it.

Talk to it right away, before writing a word of your own:

```bash
uv run convo console --tenant <your-id> --project example --text
```

## 2. What each file owns (5 minutes)

| file | what it owns |
|---|---|
| `tenant.py` | the id, the name, the region, and **which systems this business runs** (`build_adapters`) |
| `adapters/bookings.py` | one class per system: `capabilities()` and `execute(capability, args)`. Replace the fakes with your HTTP calls and nothing above changes |
| `projects/<p>/project.py` | the use case: a `ToolSpec` per capability (`side_effect`, `idempotency_key`, `compensation`, `timeout_s`), the voice, the failure sentences, the knowledge seed |
| `projects/<p>/prompts/knowledge.md` | the stable sheet the prompt opens with. **Make it longer than 4096 tokens** or Haiku 4.5 caches nothing, and never put a date or a reference in it |
| `projects/<p>/prompts/` | one Markdown view per stage (role, `<instructions>`, `<examples>`), `<stage>/confirm.md` for what ConfirmTask asks with, a `_`-prefixed folder such as `_partials/` for paragraphs stages share. The register — *usted* or *tú* — lives here and nowhere else |
| `projects/<p>/stages/` | one `TenantAgent` per phase of the call, each with its own `@function_tool` methods. A tool's docstring **is** the schema the model reads |
| `projects/<p>/helpers.py` | the pure helpers the stages share: how a row is read aloud, how a spoken hour is parsed |
| `projects/<p>/messages.py` | every sentence a tool hands the model when it cannot do what was asked, and the four failure sentences |
| `projects/<p>/evals/` | `goldens.json`, `metrics.py` (thresholds included), `dag.py` (tool names, criteria wording, register and neighbour word lists), `grounding.py` (what your agent can be wrong about) |

Three rules the template already follows and a copy should keep:

1. **Identity travels between stages, state does not.** `summary()` says *which*
   booking the call is about; the next stage asks the system for its status.
2. **The confirmation sentence is rendered by us, never written by the model**
   (`helpers.confirmation_question`). What the customer agreed to and what the
   platform then does are the same string by construction.
3. **Anything irreversible is declared irreversible.** The guard refuses it
   without a token that `ConfirmTask` mints from a real yes. Two writes instead
   of one? Wrap them in a `Saga` and declare a `compensation` — see
   `tenants/tienda-sur/projects/pedidos/stages/order_desk.py`.

## 3. What you never touch

The platform owns the runtime, and a tenant that reaches into it is a tenant
that breaks on the next release: routing (`convo/session/router.py`), the registry, the
session, the tool executor, guard, saga, the event log, the providers, the prompt
layout (`convo/prompting/`) and the eval *shapes* (`convo/testing/`). Projects import
`convo.agents` — never `livekit.agents` — so the framework stays replaceable from one package.
`docs/tenants.md` is the full table of who owns what.

## 4. Its evals (3 minutes)

`evals/goldens.json` is one entry per behaviour you care about: `input`, the
`expected_behaviour` a judge reads, `expected_tools` (an empty list is a real
expectation — "this turn must call nothing"), and `before` for the turns that
only get the call to the right stage.

Add your project to a suite under `tests/evals/` — copy
`tests/evals/test_pedidos_deepeval.py`, which runs one conversation per golden
and scores it with the deterministic metrics first and the one judge call last.
Then:

```bash
uv run pytest -m unit                      # free: no judge, no key
uv run deepeval test run tests/evals -n 3  # needs ANTHROPIC_API_KEY
```

`docs/evals.md` explains every metric and §7 is the checklist for adding one.

## 5. Before you call it done

- [ ] every `TODO(copy)` replaced (`grep -rn 'TODO(copy)' tenants/<your-id>`)
- [ ] the knowledge block is over 4096 tokens and has no dates or ids in it
- [ ] every tool your project declares has an adapter that can actually serve it
- [ ] the register word list in `evals/dag.py` matches how your business speaks
- [ ] the neighbour word list (`OTHER_BUSINESS_TERMS`) names the other tenants
- [ ] `uv run pytest -m unit` green, and one golden per behaviour you care about
