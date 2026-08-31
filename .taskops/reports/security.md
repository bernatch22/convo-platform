# Security posture — a platform that talks to strangers over the phone

A contact-center platform accepts calls from the open PSTN, mints browser
credentials for anonymous visitors, and runs a language model that can trigger
irreversible actions. Every one of those is an attack surface, and each was
designed against from the first line of code — not bolted on. This document is
the map of the defences and *why* each exists.

## The threat model, in one picture

```
        UNTRUSTED                        TRUST BOUNDARY                 TRUSTED
  ┌──────────────────┐              ┌──────────────────────┐    ┌──────────────────┐
  │  the open PSTN   │──SIP/RTP────▶│  carrier IP allowlist │    │  the worker      │
  │  (any caller)    │              │  + hide_inbound_port  │───▶│  (one process    │
  ├──────────────────┤              ├──────────────────────┤    │   per call)      │
  │  a web visitor   │──WebRTC─────▶│  api.py mints a JWT   │    │                  │
  │  (anonymous)     │              │  scoped to ONE room   │───▶│  guard + saga +  │
  ├──────────────────┤              ├──────────────────────┤    │  append-only log │
  │  the LLM's output│──tool call──▶│  ToolSpec + guard     │───▶│                  │
  │  (non-determin.) │              │  confirmation token   │    │                  │
  └──────────────────┘              └──────────────────────┘    └──────────────────┘
        who they are is                 the fence is a            secrets live only
        NEVER inferred                  signed grant, never       in env, never in
        from what they say              a claim in a payload      git or a transcript
```

The single principle behind all of it: **identity and authority come from a
cryptographically-signed grant, never from data the untrusted side sends.**

## 1. The telephone edge — the loudest door

A public SIP port is scanned continuously by the whole internet within hours of
opening; SIP scanners probe for open relays and try SQL-injection strings in
the `From` header. So the telephone edge is locked at four layers, and no call
is ever accepted on fewer:

```
  a call from Twilio                        a scanner from anywhere
        │                                          │
        ▼                                          ▼
  ┌───────────────────── LAYER 1: cloud firewall ─────────────────────┐
  │  UDP/TCP 5060 ACCEPTS ONLY Twilio's 8 published signalling CIDRs.  │
  │  Everything else is DENIED at the network edge — the packet never  │
  │  reaches the box. (An explicit DENY rule, so no established flow    │
  │  survives a rule change.)                                          │
  └────────┬──────────────────────────────────────────────┬───────────┘
           │ passes                                        │ dropped here
           ▼                                               ✗
  ┌───────────────────── LAYER 2: hide_inbound_port ──────┐
  │  livekit-sip DROPS any INVITE that does not present    │
  │  the trunk's declared number+auth. No 4xx, no reply —  │
  │  a scanner learns nothing.                             │
  └────────┬───────────────────────────────────────────────┘
           ▼
  ┌───────────────────── LAYER 3: inbound trunk allowlist ┐
  │  the SIPInboundTrunk accepts only our number, only from│
  │  the same carrier ranges — a second, independent check.│
  └────────┬───────────────────────────────────────────────┘
           ▼
  ┌───────────────────── LAYER 4: dispatch by number ─────┐
  │  the number resolves to a tenant through the routes     │
  │  table. An unknown number is unroutable, not a default. │
  └─────────────────────────────────────────────────────────┘
```

**Why carrier-only, not open:** media (RTP) can legitimately arrive from any of
the carrier's media IPs, so the RTP range stays open — but *signalling* only
ever comes from the carrier's signalling ranges, and without a valid INVITE the
open media ports are unreachable. Locking 5060 to the carrier turns "the whole
internet can knock" into "only our carrier can knock", which is the entire
difference between a flooded port and a quiet one.

**Cost containment is part of security here.** A dropped INVITE creates no room,
so no job, so no worker, so **zero LLM/STT/TTS spend** — a rejected scan is free.
Toll-fraud (the classic SIP attack) is structurally impossible: the platform
only ever dials *out* through a warm-transfer path a supervisor initiates, never
on the model's say-so.

## 2. Telephony-account hygiene — working WITH the carrier's fraud systems

Carrier anti-fraud systems cannot tell a legitimate automated agent from an
attacker — the *pattern* is the signal, not the intent. Provisioning telephony
therefore follows rules that keep our own automation from looking like an
account takeover:

- **Credentials never touch git, a `.md`, or a transcript.** The source of truth
  is a `0600` file outside every synced path; boxes read from env only. Rotation
  is a documented checklist across every consumer (`credentials/twilio.txt` →
  local envs → each box's env → service restart), so a key change is atomic.
- **API-key auth over long-lived account tokens** where the SDK supports it: a
  scoped `SK…`/secret pair can be revoked without touching the account token.
- **Onboarding is gradual and idempotent** — trunks are created once and reused,
  never create-delete-recreate loops, and call volume ramps rather than bursts.
- **A suspension playbook exists in advance**: a carrier may pause an account
  precautionarily, so the remediation path (verify identity → rotate → restart)
  is written down before it is ever needed, and the trunk/number survive it.

## 3. The web edge — one JWT, one room

A LiveKit API key can sign a token for *any* room, so the token itself is the
tenant fence — not the SFU:

```
  browser ──POST /token {tenant, project, channel}──▶ api.py
                                                        │ validates against the registry
                                                        ▼
        JWT: room = "tenant-project-<uuid>"  ← EXACT string, never a wildcard
             can_publish scoped to the channel (chat = no audio at all)
             RoomAgentDispatch(metadata) = who this call is for, signed
                                                        │
  browser ──joins ONLY that room──────────────────────▶ SFU
```

- **The room grant is an exact string.** A token minted for tenant A's room
  cannot join tenant B's — cross-tenant isolation is one line, enforced by the
  signature.
- **The channel is in the grant.** A chat session is minted with audio off both
  ways, so a chat visitor cannot open a microphone track even if the client is
  tampered with — and, proven by test, the worker opens *zero* STT/TTS provider
  connections for a chat channel.
- **Observers are publish-nothing and hidden.** A supervisor's token carries
  `can_publish=false` and `hidden=true`: they can never be heard by the caller
  and never speak until an explicit, separately-granted takeover.

## 4. The LLM edge — the model is untrusted output

The model's output is treated as an untrusted actor. It can *ask* for anything;
what actually runs is gated:

```
  model: "call cancel_appointment(id=…)"
        │
        ▼
  ┌──────────────── guard.check(ToolSpec, args, tc) ────────────────┐
  │  side_effect: read      → runs                                   │
  │  side_effect: write     → runs, logged                          │
  │  side_effect: irreversible → REFUSED unless a confirmation_token │
  │      minted by ConfirmTask authorises THIS EXACT call            │
  └──────────────────────────────┬───────────────────────────────────┘
                                 ▼
            the token's audience = sha256(tool + canonical args)
            → a "yes" authorises exactly one call, once, and expires
```

- **Irreversible actions need a spoken confirmation** turned into a single-use
  token bound to the exact tool and arguments — a "yes" to cancel order 123 can
  never authorise cancelling order 456, and a token is consumed on use.
- **PII is masked by declaration, in the audit.** Each `ToolSpec` declares its
  `pii_scope`; the log masks those values by name *and* by value everywhere they
  appear — the SMS text in the log reads `An*************` while the gateway
  still receives the real name.
- **The prompt carries no secrets and no injected authority.** A supervisor's
  whisper is appended to context only after the worker verifies `role=supervisor`
  in the signed token — never because a data message claimed to be one.
- **Tool failures are contained**: a tool raises `ToolError` (the model sees it);
  any other exception is hidden by the framework and logged, never surfaced.

## 5. The audit — SIGKILL-safe, append-only, per-session

Security you cannot prove after the fact is theatre. Every session writes an
append-only log with a per-session `seq`, flushed to disk on every event (a
process killed mid-call leaves a log that ends exactly where the call did).
SQLite triggers refuse UPDATE and DELETE on the events table. The consent chain
is *visible*: `confirm.granted` (seq N) provably precedes the irreversible
`tool.call` (seq M), joined on the confirmation token's audience, not on
adjacency — on screen and in the guard.

## Where we stand

| Surface | Control | Failure mode it removes |
|---|---|---|
| PSTN signalling | carrier-CIDR firewall + hide_inbound_port + trunk allowlist | scanner floods, toll fraud, unrouted calls |
| PSTN spend | no room → no job → no cost on a rejected call | pay-per-scan |
| Carrier account | keys off-git, API-key auth, gradual onboarding, rotation playbook | credential leak, precautionary suspension |
| Web tokens | exact-room JWT, channel-scoped grants | cross-tenant join, unexpected mic |
| Observers | publish-nothing, hidden | a supervisor heard by the caller |
| Tool calls | ToolSpec + guard + single-use confirmation token | the model taking an irreversible action alone |
| PII | masked by declaration, name and value | a DNI next to a name in the audit |
| Audit | append-only, per-seq, SIGKILL-safe, triggers refuse edits | a tampered or truncated record |

The rule underneath every row is the same: **authority is a signed grant, never
a claim in a message; and the untrusted side is never asked to be honest.**
