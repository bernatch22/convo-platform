# convo-platform

A multi-tenant conversational platform for contact centers — voice and chat —
built on self-hosted [LiveKit](https://livekit.io) (SFU + SIP + Agents),
Anthropic Claude Haiku, Soniox STT and ElevenLabs TTS. One deploy serves many
businesses; the LLM is a swappable interface driver, the platform is a process
runtime that talks.

Built in public as an architecture exercise: the design is in
[`REPORT.md`](REPORT.md), the working rules in [`CLAUDE.md`](CLAUDE.md), and
every step of the build lives on a public taskops board (milestones = chapters,
cards = briefs). Each milestone ships an HTML usage report under `reports/`.

## Run

```bash
uv sync --extra dev
cp .env.example .env            # add your keys (Anthropic, Soniox, ElevenLabs)
pytest -m unit                  # fast tests, no keys needed
python worker.py --help         # the LiveKit Agents CLI (console/dev/start)
```

From ms-1: `python worker.py console --text` talks to the agent in the terminal.

## Layout

```
worker.py     data plane: one AgentServer, one fleet, every tenant
api.py        control plane (ms-8+): tokens, dispatch, tools hub, call log
core/         runtime: contracts, agents, tools, adapters, state, observability
tenants/      one folder per customer: adapters + projects (agents, prompts, evals)
tests/        unit tests and ring-1 evals
reports/      per-milestone HTML reports for reviewers
presentation/ self-narrating deck engine
```

License: Apache-2.0.

## How this repository is orchestrated

The build itself is public. A [taskops](https://pypi.org/project/taskops-cli/)
board holds the plan; this repo carries the board's hooks (`.claude/`,
`.mcp.json`) so any clone can join it.

- **Milestones are chapters.** Each one is small enough for a human to review
  in minutes and ends with a command to run plus `reports/ms-N.html`, a
  self-contained page explaining what was built and how to try it.
- **Cards are briefs.** A card carries a spec a stranger could pick up, the
  files it may touch, acceptance criteria, and — when a decision was made — a
  short essay in its thread explaining why.
- **One orchestrator, many workers.** The orchestrator plans, assigns (each
  card gets its own git worktree), reviews the diff in session and merges with
  `--no-ff`. Workers are AI sub-agents, one per brief; the first infrastructure
  cards were done by the orchestrator itself.
- **Humans judge.** Every milestone report leaves an `nvim -p …` command to
  read the code; evaluations (DeepEval) run on every milestone so prompts keep
  a consistent line as the system grows.

Reusable for other teams: the hooks are two lines of JSON, the conventions are
this section, and the pattern (seams first, then parallel cards, HTML report
per milestone) does not depend on any particular framework.
