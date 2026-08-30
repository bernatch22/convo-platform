# convo-platform

[![ci](https://github.com/bernatch22/convo-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/bernatch22/convo-platform/actions/workflows/ci.yml)

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
