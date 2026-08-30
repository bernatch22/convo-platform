# Milestone reports

One report per milestone, written when it lands. Not a changelog and not a
manual: what we set out to do, what we actually achieved, what we learned the
hard way, the decisions we took and why, where the project stands, and what
comes next. Written so that a person or an agent picking the project up cold
understands how we got here.

How to try things lives in `README.md`; the design in `REPORT.md`; how the
agent is measured in `docs/evals.md`; per-card detail on the board. Generated artifacts (DeepEval HTML, recordings, usage
sheets) live under `tmp/reports/` and are not versioned.

| Milestone | Status | Report |
|---|---|---|
| ms-0 skeleton — repo, toolchain, contracts, CI | landed | [ms-0.md](ms-0.md) |
| ms-1 LLM in text — talk to Claude Haiku from the terminal | landed | [ms-1.md](ms-1.md) |
| ms-2 one tool with a contract — the LLM calls a fake adapter | landed | [ms-2.md](ms-2.md) |
| ms-3 stages + confirmation — Identify → ChooseSlot → Farewell, ConfirmTask, saga | landed | [ms-3.md](ms-3.md) |
| ms-4 event log — append-only with seq, session report, `convo sessions` CLI | landed | [ms-4.md](ms-4.md) |
| ms-5 tenants — one worker, two businesses | landed | [ms-5.md](ms-5.md) |
| ms-6 local voice — talk to the agent with your microphone | landed | [ms-6.md](ms-6.md) |
| ms-7 evals ring 1 complete — DeepEval suites per project in CI | deferred to the end | — |
| ms-8 LiveKit server locally — rooms, tokens, dispatch by metadata | landed | [ms-8.md](ms-8.md) |
