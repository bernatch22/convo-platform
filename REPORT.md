# Conversational Transactional Platform — Architecture Report

> Technical design for a multi-tenant, transactional conversational platform for
> contact centers (voice and chat), prepared for the *Principal Platform
> Architect* challenge. Every claim links to code in this repository or to a
> verified source (see Appendix A). The public taskops board records how the
> design was built and why.

_Resumen en español al final (Apéndice C)._

## 0. Executive summary
_TODO — thesis, three planes, what the demo proves._

## 1. High-level architecture
_TODO — C4 container diagram: channels → LiveKit (SFU+SIP) → workers → control plane → tools (local/remote) → customer systems._

## 2. Bounded contexts
_TODO — Session, Process, Tools & Adapters, Tenancy & Config, Audit, Evaluation, Supervision._

## 3. Execution model of a conversation
_TODO — sequence: STT interim → turn → LLM → tool → ConfirmTask → saga/compensation → handoff; per-turn latencies._

## 4. Tools and contracts
_TODO — ToolSpec; guard; catalog; local vs remote execution._

## 5. Transactional orchestration
_TODO — sagas with human confirmation as a step; compensation; idempotency._

## 6. State management
_TODO — append-only event log with seq; snapshots; re-engagement (not resumption)._

## 7. Per-client / per-project configuration
_TODO — tenants/ (code) vs routes/project_versions (data); fleets; canary._

## 8. Integration strategy with external systems
_TODO — Adapter ports, registry, REST generic adapter; tenant-sdk (outbound WS, no webhooks)._

## 9. Observability, audit, replay and QA
_TODO — OTel spans; session report; call log v3; three evaluation rings (DeepEval + LiveKit)._

## 10. Security and privacy
_TODO — JWT per tenant, room prefix, PII at the edge, crypto-shredding, isolation tiers._

## 11. Cloud infrastructure and deployment
_TODO — self-hosted LiveKit box (compose), workers, no GPU, cost per call._

## 12. Roadmap
_TODO — milestones as executed on the public board._

## 13. Trade-offs
_TODO — LiveKit vs Pipecat vs managed; Haiku; local vs remote tools; self-host cost; what we deliberately do not build._

## Appendix A — Evidence index
_TODO — claim → file:line._

## Appendix B — Provider configuration
_TODO — Soniox / ElevenLabs / Anthropic parameters and why._

## Apéndice C — Resumen en español
_TODO._
