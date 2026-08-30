# ms-0 — skeleton: repo, toolchain, contracts, CI

**Landed 2026-08-30 · 3 cards · master `82b4397`**

## What we set out to do

Give every later card stable ground: a public repository a stranger can clone
and run, the package layout, and the contracts the whole platform is built on
— before any behaviour exists. Seams first, serialized; everything else
branches from them.

## What we achieved

- A `uv`-managed Python 3.12 project on `livekit-agents` 1.7 with the
  Anthropic, Soniox, ElevenLabs and Silero plugins, `deepeval`, `pytest`, `ruff`.
- `worker.py`: one `AgentServer`, one fleet (`FLEET`, default `cc`), the
  `rtc_session` entrypoint wired and deliberately unimplemented.
- The contracts, with docstrings and no behaviour: `TenantContext` (the one
  object a session carries), `SessionMeta` (what a dispatcher tells a worker;
  unknown fields ignored), `ToolSpec`/`SideEffect` (irreversible tools need a
  confirmation token; `pii_scope` names what to mask), `Adapter` (the port to a
  customer's systems), `Event` (one numbered line of the session log).
- Two tests that protect the rules: `core` never imports `tenants`, and the
  contract invariants hold.
- CI (ruff + unit tests), portable taskops hooks, README with the
  orchestration model.

## What we learned

- **The board needs a root commit.** `taskops_assign` cuts branches from
  `HEAD`; an empty repo cannot host a milestone. Initial commit first.
- **`~/.taskops/board.json` hijacks the project root.** A stray HOME marker made
  `taskops init` put the board in `$HOME` (second time this bites). Rename the
  marker, re-init inside the repo, gitignore `.taskops/*` except reports.
- **zsh `noclobber` silently skips `cat > existing`.** Several rewrites did not
  happen and one temporary `import tenants` reached a commit before the test
  caught it. Every shell step now starts with `setopt clobber`; files are
  rewritten with Python when in doubt.
- **The isolation test earns its keep immediately.** It failed on the first
  registry draft (a static `import tenants`) — the fix (folder discovery +
  `importlib` by name) is the shape the registry should have had anyway.
- **`taskops init` writes machine-specific absolute paths** into
  `.claude/settings.json` and `.mcp.json`; a public repo needs the `uvx --from
  taskops-cli …` form.

## Decisions

- Root holds exactly two loose Python files: `worker.py` (data plane) and
  `api.py` (control plane, later). Everything else lives in packages.
- Contracts are dataclasses (internal) or pydantic (crossing a process).
- Reports are narrative Markdown here; generated artifacts go to `tmp/`.

## Where we stand

Nothing converses yet. `pytest -m unit` is green (7 tests), `python worker.py
--help` shows the LiveKit CLI, `console` fails with the ms-0 message by design.

## Next

ms-1: the first conversation — Claude Haiku in text from the terminal, one
tenant, one prompt, and the first DeepEval check on that prompt.
