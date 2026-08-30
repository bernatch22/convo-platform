# ms-8 — a real server: rooms, tokens, and dispatch by metadata

**Landed 2026-08-30 · 3 cards (2 by the orchestrator, 1 by an Opus worker) · lands on master with this milestone**

## What we set out to do

Give the platform its first server. Until now every session was a laptop
process talking to itself; ms-8 stands up the LiveKit SFU locally (docker),
grows `api.py` into a real control plane door (`POST /token`, `GET /tenants`),
and proves the routing thesis end-to-end: one worker process, no `TENANT` in
its environment, serving two different businesses because the JWT said so.
And after the morning's incident, one non-negotiable piece of hygiene: a unit
ring that is structurally incapable of calling a provider.

## What we achieved

- **`docker compose -f infra/compose/dev.yml up`** boots livekit-server 1.9.1
  (dev keypair, fixed ports, media muxed on one UDP port) + redis. Only the
  server is containerised; api.py and the worker run on the host.
- **The token is the tenancy.** `POST /token {tenant, project, channel}`
  validates against the registry and mints a JWT whose room grant is an exact
  string (a LiveKit API key signs for *any* room — this line is the fence) and
  whose `RoomAgentDispatch` carries `agent_name=FLEET` plus the same
  `SessionMeta` JSON `core.router.resolve` already reads. Who a session is for
  is decided once, at the door.
- **One worker, two businesses, zero env.** `env -u TENANT -u PROJECT
  worker.py dev` + `scripts/dev_call.py`: clinica-norte greeted as a clinic,
  tienda-sur found order TS-10432 and named the carrier — sessions
  `AJ_swAANZTA6Lty` / `AJ_Xpi2Y6tRLdcK`. The env fallback defaults to
  clinica-norte, so tienda-sur can only have come through the SFU's dispatch.
- **Chat is a room option, not a project.** `channel_options("chat")` meets
  the room with `RoomOptions(audio_input=False, audio_output=False)`; a chat
  session must not hold a microphone permission nobody asked for.
- **Ring 3 crossed the SFU.** `convo sessions eval` and
  `tests/evals/test_dispatch_ring.py` judge the *routed* sessions with the
  same DAGs as the goldens: consent 1.0 on both tenants (4 passed).
- **The unit suite went from 4 minutes to 1.6 seconds.** Not an optimisation —
  a diagnosis (below).

## What we learned the hard way

1. **The judge-backed unit tests were phoning Anthropic on every run.** The
   4-minute "fast" suite was 18 tests quietly making real LLM calls — money
   and minutes on every `pytest -m unit`, for months of runs. The morning's
   incident (a new judged test hung the suite; timed-out reruns piled up four
   zombie pytests) was the same disease, acute form. The fix is structural,
   not disciplinary: an autouse fixture swaps `ANTHROPIC_API_KEY` for a dead
   sentinel inside every unit test not marked `needs_llm` — clients still
   construct (plenty of unit tests build sessions), but a real request dies
   in seconds with a 401. STT/TTS keys are stripped the same way unless
   marked `voice`. A misplaced test now *fails fast* instead of hanging.
2. **`rtc.node_ip` or nothing connects.** Without it, livekit-server in
   docker advertises its compose-network address (`172.24.0.3`) as its ICE
   candidate — unroutable from a macOS host. Signalling looks perfectly
   healthy; every single peer connection times out, worker and client alike.
   `node_ip: 127.0.0.1` (the published ports are what really reach the
   container). Nothing on this stack could ever have connected without it.
3. **A worktree without `.env` silently changes what a suite means.** The
   18 `needs_llm` tests skip without a key — a green run that proved less
   than it seemed. The closing runs say explicitly which rings ran.
4. **`pytestmark` lists constrain marker design.** `needs_llm` as a helper
   *function* broke `pytestmark = [pytest.mark.unit, needs_llm]` at collection.
   It is a plain marker now, with a `pytest_collection_modifyitems` hook for
   the skip — composable both as a decorator and in a list.
5. **A local redis was already on 6379.** The compose redis publishes no port
   at all: only livekit talks to it, inside the compose network. Publish
   nothing you don't need — it was never a feature, just a collision.

## Decisions

- **Raw `livekit-client` for the web (ms-9/14), no components package.** The
  components hide exactly the flow this test judges (token → dispatch → room
  → tracks); production voice platforms wrap the core SDK themselves, and our
  ~120-line hook will be readable in one nvim tab. Decided with the human.
- **A minimal SIP card lands EARLY in ms-11** (livekit + sip on the GCP box
  only): Twilio needs a public UDP SIP endpoint and a laptop has none —
  `btunnel` is HTTP/WS and cannot carry RTP. The full box (Caddy, MinIO,
  shipway) stays ms-10. `lk.bernardocastro.dev` is the reserved name.
- **Evals milestones (ms-7, ms-13) move to the end** — the human's order.
  The per-card DeepEval increments continue regardless; that is what keeps
  the prompts on a consistent line. Consequence: the date/time hotfix
  (04c2d8e) sits on the ms-7 branch and reaches master when ms-7 lands.
- **The dead-sentinel key beats deletion.** Deleting the key broke every
  unit test that constructs a session; the sentinel keeps construction
  working and turns any real call into an instant, loud failure.

## Where we stand

Master (with this landing) runs the full loop a customer deployment runs:
a token minted by the control plane, a room on a real SFU, a worker
dispatched by metadata, two tenants on one process, the session logged,
judged and costed. What a laptop cannot do is answer a phone — that is ms-11,
with the minimal SIP box first. The known debts are on the board:
chat sessions still open an unused Soniox websocket (tk-fab816, front of
ms-9) and the LiveKitConnector voice smoke belongs to ms-13.

Try it (three terminals + one script):

```bash
docker compose -f infra/compose/dev.yml up
uv run uvicorn api:app --port 8090
env -u TENANT -u PROJECT uv run python worker.py dev
uv run python scripts/dev_call.py            # both tenants, back to back
uv run python -m convo sessions list         # the two routed sessions
```

## What comes next

**ms-11 first card** — livekit + sip on the GCP box, `lk.bernardocastro.dev`,
firewall for SIP/RTP; then Twilio's elastic trunk pointing at it and a phone
that rings. **ms-9+14** — the React UI (raw livekit-client, react-router data
router): Talk, Sessions, the seq timeline with the consent proof on screen.
